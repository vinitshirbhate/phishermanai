/**
 * PhishermanAI content script for WhatsApp Web.
 *
 * DESIGN CONSTRAINTS — these are compliance requirements, not preferences.
 * Read docs/PRIVACY.md before changing anything here.
 *
 *  1. USER-INITIATED ONLY. Nothing is read or sent until the user clicks
 *     "Check this" on one specific message. There is no background scanning,
 *     no bulk reading of a chat, and no periodic sweep of the DOM for content.
 *
 *  2. NEVER WRITES TO WHATSAPP. This script does not send messages, reply,
 *     forward, auto-populate the composer, or click anything on the user's
 *     behalf. Automating the WhatsApp client is what WhatsApp's Terms of
 *     Service prohibit, so we do not do it at all. The extension only adds its
 *     own UI on top of the page and reads the one message the user picked.
 *
 *  3. DATA MINIMISATION. Only the text of the chosen message is sent, and only
 *     after phone numbers and e-mail addresses in it are redacted locally. We
 *     never read the contact list, chat titles, other messages, or the user's
 *     own phone number.
 *
 *  4. USER-CONTROLLED DESTINATION. The message goes to the endpoint the user
 *     configured, which defaults to their own machine (127.0.0.1:8000). No
 *     third-party server is contacted, and there is no telemetry.
 *
 *  5. NOTHING IS STORED. The verdict is rendered into a panel and discarded on
 *     close. No message content is written to extension storage.
 */

(() => {
  "use strict";

  const BUTTON_CLASS = "phai-check-btn";
  const PANEL_ID = "phai-panel";

  let consentGiven = false;
  let endpoint = "http://127.0.0.1:8000";

  chrome.storage.local.get(["consent", "endpoint"], (cfg) => {
    consentGiven = cfg.consent === true;
    if (cfg.endpoint) endpoint = cfg.endpoint;
  });

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.consent) consentGiven = changes.consent.newValue === true;
    if (changes.endpoint) endpoint = changes.endpoint.newValue;
  });

  // ------------------------------------------------------------------
  // Local redaction, applied BEFORE anything leaves the browser.
  // ------------------------------------------------------------------
  // Fraud detection needs the claims, the links and the payment handles. It
  // does not need to know who sent the message, so identifiers that are purely
  // personal are removed here rather than trusted to the server.
  //
  // A UPI address is deliberately NOT redacted: it is the destination of the
  // money and the single strongest fraud signal we have. A bare phone number
  // is redacted; "9876543210@ybl" is kept, because that is a payment address.
  function redact(text) {
    return text
      .replace(/(?<![\w@.])(?:\+?91[\s-]?)?[6-9]\d{9}(?![\w@])/g, "[phone redacted]")
      .replace(/\b[\w.+-]+@(?:[\w-]+\.)+[a-z]{2,}\b/gi, "[email redacted]");
  }

  // ------------------------------------------------------------------
  // Reading exactly one message
  // ------------------------------------------------------------------
  function extractMessageText(bubble) {
    // WhatsApp Web marks message text with .selectable-text / copyable-text.
    // Several selectors are tried because the markup changes between releases;
    // all of them are read-only.
    const selectors = [
      "span.selectable-text",
      "div.copyable-text span",
      "[data-pre-plain-text] span",
    ];
    for (const selector of selectors) {
      const nodes = bubble.querySelectorAll(selector);
      if (nodes.length) {
        return Array.from(nodes)
          .map((n) => n.innerText)
          .join("\n")
          .trim();
      }
    }
    return (bubble.innerText || "").trim();
  }

  function isForwarded(bubble) {
    const text = (bubble.innerText || "").toLowerCase();
    return text.includes("forwarded");
  }

  // ------------------------------------------------------------------
  // Verdict panel
  // ------------------------------------------------------------------
  function closePanel() {
    document.getElementById(PANEL_ID)?.remove();
  }

  function renderPanel(state, payload) {
    closePanel();
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "phai-panel";

    if (state === "consent") {
      panel.innerHTML = `
        <div class="phai-head phai-neutral">
          <strong>PhishermanAI</strong>
          <button class="phai-close" aria-label="Close">&times;</button>
        </div>
        <div class="phai-body">
          <p><strong>Before the first check</strong></p>
          <p>This will send the text of the message you selected to
             <code>${escapeHtml(endpoint)}</code> — by default your own computer.</p>
          <p>Phone numbers and email addresses are removed before sending.
             Nothing else from WhatsApp is read: not your contacts, not other
             messages, not your own number. The extension never sends or replies
             to messages.</p>
          <button class="phai-btn phai-primary" id="phai-consent">I understand — enable checking</button>
        </div>`;
      panel.querySelector("#phai-consent").addEventListener("click", () => {
        chrome.storage.local.set({ consent: true }, () => {
          consentGiven = true;
          closePanel();
        });
      });
    } else if (state === "loading") {
      panel.innerHTML = `
        <div class="phai-head phai-neutral">
          <strong>PhishermanAI</strong>
          <button class="phai-close" aria-label="Close">&times;</button>
        </div>
        <div class="phai-body"><p>Checking against SEBI registrations and exchange filings…</p></div>`;
    } else if (state === "error") {
      panel.innerHTML = `
        <div class="phai-head phai-neutral">
          <strong>PhishermanAI</strong>
          <button class="phai-close" aria-label="Close">&times;</button>
        </div>
        <div class="phai-body">
          <p><strong>Could not reach the verifier.</strong></p>
          <p class="phai-muted">${escapeHtml(payload)}</p>
          <p class="phai-muted">Is the API running at <code>${escapeHtml(endpoint)}</code>?
             Start it with <code>uvicorn api.main:app</code>.</p>
        </div>`;
    } else {
      const v = payload;
      const tone = {
        GENUINE: "phai-genuine",
        TAMPERED: "phai-tampered",
        UNVERIFIED: "phai-unverified",
        FRAUDULENT: "phai-fraud",
      }[v.verdict] || "phai-neutral";

      // What the user reads. "UNVERIFIED" sounds like the sender failed a
      // check; they did not -- we simply hold no record of them, which is the
      // ordinary outcome for legitimate mail from a company outside our
      // registry. The label should report what we found, not imply blame.
      const label = {
        GENUINE: "VERIFIED",
        TAMPERED: "TAMPERED",
        UNVERIFIED: "NO RISK FOUND",
        FRAUDULENT: "FRAUDULENT",
      }[v.verdict] || v.verdict;

      const reasons = (v.reasons || [])
        .filter((r) => r.severity >= 3)
        .slice(0, 4)
        .map((r) => `<li>${escapeHtml(r.message)}</li>`)
        .join("");

      const altered = (v.field_comparisons || []).filter((c) => c.match === false);
      const tamperBlock = altered.length
        ? `<div class="phai-tamper">
             ${altered
               .map(
                 (c) => `
               <div class="phai-tamper-row">
                 <div class="phai-tamper-label">${escapeHtml(c.field.replace(/_/g, " "))}</div>
                 <div><span class="phai-muted">this message says</span>
                      <b class="phai-bad">${escapeHtml(String(c.extracted_value))}</b></div>
                 <div><span class="phai-muted">${escapeHtml(
                   v.matched_filing?.company_name || "the company"
                 )} filed</span>
                      <b class="phai-good">${escapeHtml(String(c.filed_value))}</b></div>
               </div>`
               )
               .join("")}
           </div>`
        : "";

      panel.innerHTML = `
        <div class="phai-head ${tone}">
          <strong>${escapeHtml(label)}</strong>
          <span class="phai-score">${v.confidence}/100 evidence</span>
          <button class="phai-close" aria-label="Close">&times;</button>
        </div>
        <div class="phai-body">
          <p class="phai-summary">${escapeHtml(v.summary)}</p>
          ${tamperBlock}
          ${reasons ? `<ul class="phai-reasons">${reasons}</ul>` : ""}
          <div class="phai-actions">
            ${
              v.warning_card_url
                ? `<a class="phai-btn" target="_blank" rel="noopener"
                      href="${escapeHtml(endpoint + v.warning_card_url)}">Get warning card</a>`
                : ""
            }
          </div>
          <p class="phai-foot">
            Checked locally. This message was not stored, and nothing was sent
            or replied to on your behalf.
          </p>
        </div>`;
    }

    panel.querySelector(".phai-close")?.addEventListener("click", closePanel);
    document.body.appendChild(panel);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  // ------------------------------------------------------------------
  // The one user-initiated action
  // ------------------------------------------------------------------
  async function checkMessage(bubble) {
    if (!consentGiven) {
      renderPanel("consent");
      return;
    }

    const raw = extractMessageText(bubble);
    if (!raw || raw.length < 8) {
      renderPanel("error", "That message has no text to check.");
      return;
    }

    renderPanel("loading");

    const text = redact(raw);
    const forwarded = isForwarded(bubble);

    chrome.runtime.sendMessage(
      { type: "PHAI_VERIFY", text, forwarded, endpoint },
      (response) => {
        if (chrome.runtime.lastError) {
          renderPanel("error", chrome.runtime.lastError.message);
          return;
        }
        if (!response || !response.ok) {
          renderPanel("error", response?.error || "Unknown error");
          return;
        }
        renderPanel("verdict", response.data);
      }
    );
  }

  // ------------------------------------------------------------------
  // Injecting the button
  // ------------------------------------------------------------------
  //
  // A button is attached to message bubbles as they appear. Attaching UI is not
  // reading content: nothing is extracted until the button is clicked. The
  // observer exists so the button appears on messages that scroll into view,
  // not to watch what people are saying.
  function decorate(bubble) {
    if (bubble.querySelector(`.${BUTTON_CLASS}`)) return;
    if (!bubble.querySelector("span.selectable-text")) return;
    // The composer uses .selectable-text too. Decorating it would put a
    // "Check this" button on the box the user types into.
    if (bubble.closest("footer") || bubble.querySelector("[contenteditable='true']")) return;

    const button = document.createElement("button");
    button.className = BUTTON_CLASS;
    button.type = "button";
    button.textContent = "Check this";
    button.title = "Verify this message with PhishermanAI";
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      event.preventDefault();
      checkMessage(bubble);
    });

    bubble.style.position = bubble.style.position || "relative";
    bubble.appendChild(button);
  }

  // Finding message bubbles without depending on WhatsApp's class names.
  //
  // WhatsApp Web now ships Meta's StyleX atomic CSS, so a message row's classes
  // look like "x10l6tqk xh8yej3 x1g42fcv" -- generated, and different between
  // releases. The old `div.message-in` / `div.message-out` selectors match
  // nothing on the current client (measured: 0 hits against 85 rows).
  //
  // Two things do survive, and both are load-bearing for accessibility rather
  // than styling, so Meta cannot obfuscate them away:
  //
  //   span.selectable-text   the message text itself
  //   [role='row']           the ARIA row wrapping each message
  //
  // So we anchor on the text and walk UP to its container, instead of guessing
  // at container class names. That also guarantees exactly one button per
  // message: several nested elements may match a container selector, but each
  // message has one text span.
  function messageContainers(root) {
    const found = new Set();
    const scope = root && root.querySelectorAll ? root : document;

    const collect = (span) => {
      const container =
        span.closest("[data-id]") ||
        span.closest("[role='row']") ||
        span.closest("div.message-in, div.message-out");
      if (container) found.add(container);
    };

    scope.querySelectorAll("span.selectable-text").forEach(collect);
    // The mutation observer hands us newly added nodes, which may themselves be
    // the text span rather than an ancestor of one.
    if (root && root.matches?.("span.selectable-text")) collect(root);

    return [...found];
  }

  function scan(root) {
    messageContainers(root).forEach(decorate);
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType === 1) scan(node);
      });
    }
  });

  function start() {
    scan(document);
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
