/*
 * extension/preflight/adapter_mv3.js - THE ONLY file in preflight/ that touches
 * chrome.* APIs. Triggers, messaging, interstitial injection. NO decision logic.
 *
 * The split is load-bearing, not stylistic: url_parse / identity / verdict are
 * pure so that eval/preflight_harness.js can exercise them under plain Node and
 * produce real verdict JSON. Every decision this file appears to make is
 * actually made in verdict.js. If you find yourself writing an `if` about risk
 * here, it belongs in verdict.js.
 *
 * BL-1 governs everything below: navigation is DEFERRED, NEVER DENIED. Every
 * interstitial has a working "Continue anyway", and if anything in this adapter
 * throws, the link proceeds. A pre-flight check that breaks the web because it
 * crashed is worse than no pre-flight check.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanPreflightAdapter = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const HOVER_MS = 400;
  const MENU_ID = "phisherman-check-link";

  // ---------------------------------------------------------------- background
  function initBackground(deps) {
    const runPipeline = deps.runPipeline;      // (url, ctx) -> verdict  (pure, injected)
    const initiated = new Map();               // tabId -> url we last saw initiated

    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
      if (!msg || msg.type !== "preflight:check") return false;
      Promise.resolve()
        .then(() => runPipeline(msg.url, msg.ctx || {}))
        .then((v) => sendResponse({ ok: true, verdict: v }))
        // BL-1: a failed check never blocks. Report the failure, allow the link.
        .catch((e) => sendResponse({ ok: false, error: String(e && e.message), verdict: null }));
      return true;                              // async response
    });

    // --- T4 context menu ---------------------------------------------------
    if (chrome.contextMenus) {
      chrome.runtime.onInstalled.addListener(() => {
        chrome.contextMenus.create({
          id: MENU_ID, title: "Check this link with Phisherman", contexts: ["link"],
        });
      });
      chrome.contextMenus.onClicked.addListener((info, tab) => {
        if (info.menuItemId !== MENU_ID || !info.linkUrl) return;
        Promise.resolve(runPipeline(info.linkUrl, { trigger: "T4" })).then((v) => {
          chrome.tabs.sendMessage(tab.id, { type: "preflight:show_panel", verdict: v });
        });
      });
    }

    if (chrome.webNavigation) {
      // --- T6 typed / pasted URL ------------------------------------------
      // MV3 cannot interstitial before navigation from here: onBeforeNavigate is
      // not blocking, and declarativeNetRequest cannot run our logic. So this is
      // a POST-HOC badge, and it is documented as such rather than dressed up as
      // prevention.
      chrome.webNavigation.onBeforeNavigate.addListener((d) => {
        if (d.frameId !== 0) return;
        initiated.set(d.tabId, d.url);
        Promise.resolve(runPipeline(d.url, { trigger: "T6", stages: ["offline"] }))
          .then((v) => chrome.tabs.sendMessage(d.tabId, {
            type: "preflight:badge", verdict: v, posthoc: true,
          }).catch(() => {}));
      });

      // --- T7 redirect landing --------------------------------------------
      // The committed URL differs from the one the user agreed to. A user who
      // cleared an interstitial for bit.ly/xyz consented to bit.ly/xyz, not to
      // wherever it landed. Re-run against the destination.
      chrome.webNavigation.onCommitted.addListener((d) => {
        if (d.frameId !== 0) return;
        const started = initiated.get(d.tabId);
        initiated.delete(d.tabId);
        if (!started || started === d.url) return;
        Promise.resolve(runPipeline(d.url, {
          trigger: "T7", redirectedFrom: started, stages: ["offline"],
        })).then((v) => chrome.tabs.sendMessage(d.tabId, {
          type: "preflight:badge", verdict: v, redirected_from: started,
        }).catch(() => {}));
      });
    }
  }

  // ------------------------------------------------------------------- content
  function initContent(deps) {
    const doc = deps.document || document;
    const send = deps.sendMessage || ((m) => chrome.runtime.sendMessage(m));
    const render = deps.render;                // {tooltip, interstitial} injectors
    let hoverTimer = null;

    function ctxFor(a) {
      return {
        anchorText: (a.textContent || "").trim().slice(0, 200),
        title: (doc.title || "").slice(0, 200),
        pageHost: location.hostname,
        pageUrl: location.href,
        surroundingText: (a.closest("p,li,td,div") || a).textContent
          ? (a.closest("p,li,td,div") || a).textContent.trim().slice(0, 600) : "",
      };
    }

    // Same-origin internal links never interstitial - a site's own navigation is
    // not a pre-flight event.
    function isInternal(a) {
      try { return new URL(a.href, location.href).hostname === location.hostname; }
      catch (e) { return true; }
    }

    // --- T1 hover >= 400 ms, offline stages only ---------------------------
    doc.addEventListener("mouseover", (e) => {
      const a = e.target && e.target.closest && e.target.closest("a[href]");
      if (!a || isInternal(a)) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => {
        send({ type: "preflight:check", url: a.href,
               ctx: Object.assign({ trigger: "T1", stages: ["offline"] }, ctxFor(a)) })
          .then((r) => { if (r && r.ok) render.tooltip(a, r.verdict); })
          .catch(() => {});
      }, HOVER_MS);
    }, true);
    doc.addEventListener("mouseout", () => clearTimeout(hoverTimer), true);

    // --- T2 left click / T3 middle or ctrl click ---------------------------
    doc.addEventListener("click", (e) => {
      const a = e.target && e.target.closest && e.target.closest("a[href]");
      if (!a || isInternal(a)) return;
      const newTab = e.button === 1 || e.ctrlKey || e.metaKey;
      if (e.button !== 0 && e.button !== 1) return;

      // DEFER, never deny. We stop the default only to insert a choice, and the
      // choice always includes continuing.
      e.preventDefault();
      const trigger = newTab ? "T3" : "T2";
      send({ type: "preflight:check", url: a.href,
             ctx: Object.assign({ trigger: trigger, stages: ["offline"] }, ctxFor(a)) })
        .then((r) => {
          const verdict = r && r.ok ? r.verdict : null;
          // L0 still shows a tooltip, not an interstitial - a wall of dialogs is
          // how users learn to click through everything.
          if (!verdict || verdict.verdict === "L0_NO_SIGNALS") return proceed();
          render.interstitial(verdict, {
            onContinue: proceed,
            onCancel: () => {},                 // stay put; nothing is blocked
          });
        })
        .catch(proceed);                        // BL-1: failure must not trap the user

      function proceed() {
        if (newTab) send({ type: "preflight:open_tab", url: a.href }).catch(() => {});
        else location.assign(a.href);
      }
    }, true);

    // --- T5 link inside a message ------------------------------------------
    // INTERFACE ONLY. Message context (chat name, sender, prior messages) is
    // supplied by the WhatsApp lane, which is NOT BUILT. Until it registers a
    // provider this returns null and no message context is attached - it does
    // not fabricate one.
    let messageContextProvider = null;
    function registerMessageContextProvider(fn) { messageContextProvider = fn; }
    function messageContextFor(anchorEl) {
      if (typeof messageContextProvider !== "function") return null;
      try { return messageContextProvider(anchorEl); } catch (e) { return null; }
    }

    return { registerMessageContextProvider: registerMessageContextProvider,
             messageContextFor: messageContextFor };
  }

  return {
    initBackground: initBackground,
    initContent: initContent,
    HOVER_MS: HOVER_MS,
    MENU_ID: MENU_ID,
  };
});
