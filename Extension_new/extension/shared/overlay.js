/*
 * extension/shared/overlay.js - ONE shadow root, positioned badges.
 *
 * NEVER WRITE INSIDE A MESSAGE NODE. WhatsApp is React: it owns those subtrees
 * and will reconcile away anything injected into them, usually at the worst
 * moment. Worse, mutating inside a row can trigger the very MutationObserver
 * that produced the badge and loop. So: a single #phisherman-layer shadow root
 * mounted as a SIBLING of the scroll container, with badges positioned
 * absolutely against message bounding boxes.
 *
 * Shadow DOM also means the host page's stylesheet cannot restyle our warnings
 * and ours cannot leak into theirs.
 *
 * Repositioning runs on requestAnimationFrame, coalesced - scroll fires far
 * faster than layout needs to.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanOverlay = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LAYER_ID = "phisherman-layer";

  const STYLE = `
    :host { all: initial; }
    .layer { position: absolute; inset: 0; pointer-events: none; z-index: 2147483000; }
    .badge {
      position: absolute; pointer-events: auto; font: 500 11px/1.4 system-ui, sans-serif;
      padding: 3px 8px; border-radius: 10px; white-space: nowrap; cursor: pointer;
      border: 1px solid rgba(0,0,0,.12); box-shadow: 0 1px 3px rgba(0,0,0,.18);
      background: #fff8e1; color: #6b4b00;
    }
    .badge[data-sev="high"]   { background: #fdecea; color: #7f1d1d; border-color: #f5c2c0; }
    .badge[data-sev="medium"] { background: #fff8e1; color: #6b4b00; }
    .badge[data-sev="low"]    { background: #eef2ff; color: #29347a; }
    .status {
      position: absolute; right: 12px; bottom: 12px; pointer-events: auto;
      font: 500 11px/1.4 system-ui, sans-serif; padding: 4px 10px; border-radius: 12px;
      background: #eef2f5; color: #33414d; border: 1px solid rgba(0,0,0,.10);
    }
    .status[data-state="BLIND"]    { background: #fdecea; color: #7f1d1d; }
    .status[data-state="DEGRADED"] { background: #fff8e1; color: #6b4b00; }
    .status[data-state="OFF"]      { background: #eceff1; color: #546e7a; }
  `;

  const SEVERITY = {
    W6_CAMPAIGN_LINKED: "high", W5_IDENTITY_MISMATCH: "high",
    W4_PAYMENT_SOLICITATION: "high", W3_TYPOLOGY_MATCH: "medium",
    W2_UNVERIFIED_ADVISORY: "medium", W1_UNSOLICITED_CONTEXT: "low",
  };
  const LABEL = {
    W6_CAMPAIGN_LINKED: "Seen elsewhere", W5_IDENTITY_MISMATCH: "Registration mismatch",
    W4_PAYMENT_SOLICITATION: "Payment request", W3_TYPOLOGY_MATCH: "Known pattern",
    W2_UNVERIFIED_ADVISORY: "No SEBI disclosure", W1_UNSOLICITED_CONTEXT: "Unsolicited group",
  };

  function create(doc, anchorSibling) {
    const existing = doc.getElementById(LAYER_ID);
    if (existing) return existing.__phisherman;

    const host = doc.createElement("div");
    host.id = LAYER_ID;
    host.style.cssText = "position:absolute;inset:0;pointer-events:none;";
    const shadow = host.attachShadow ? host.attachShadow({ mode: "open" }) : null;
    const style = doc.createElement("style");
    style.textContent = STYLE;
    const layer = doc.createElement("div");
    layer.className = "layer";
    if (shadow) { shadow.appendChild(style); shadow.appendChild(layer); }
    else { host.appendChild(style); host.appendChild(layer); }

    // SIBLING of the scroll container, never a child of a message node.
    const parent = anchorSibling && anchorSibling.parentElement;
    if (parent) {
      if (getComputedStyle && getComputedStyle(parent).position === "static") {
        parent.style.position = "relative";
      }
      parent.appendChild(host);
    } else if (doc.body) {
      doc.body.appendChild(host);
    }

    const badges = new Map();          // message_id -> {el, node}
    let statusEl = null;
    let raf = null;

    function _reposition() {
      raf = null;
      const base = host.getBoundingClientRect();
      for (const [id, rec] of badges) {
        // A message that left the DOM takes its badge with it.
        if (!rec.node || !rec.node.isConnected) { rec.el.remove(); badges.delete(id); continue; }
        const r = rec.node.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) { rec.el.style.display = "none"; continue; }
        rec.el.style.display = "";
        rec.el.style.top = (r.top - base.top) + "px";
        rec.el.style.left = (r.left - base.left) + "px";
        rec.el.style.transform = "translateY(-100%)";
      }
    }

    function schedule() {
      if (raf !== null) return;
      raf = (typeof requestAnimationFrame !== "undefined")
        ? requestAnimationFrame(_reposition) : setTimeout(_reposition, 16);
    }

    const api = {
      host: host,
      /** W0 must never reach here — the caller checks `verdict.badge` first. */
      addBadge: function (messageNode, verdict, onClick) {
        if (!verdict || !verdict.badge) return null;
        const id = verdict.message_id || String(badges.size);
        api.removeBadge(id);
        const el = doc.createElement("div");
        el.className = "badge";
        el.setAttribute("data-sev", SEVERITY[verdict.verdict] || "low");
        el.setAttribute("role", "button");
        el.setAttribute("tabindex", "0");
        el.textContent = LABEL[verdict.verdict] || "Check";
        el.title = (verdict.codes || []).map((c) => c.summary).filter(Boolean).join(" ");
        if (onClick) el.addEventListener("click", () => onClick(verdict));
        layer.appendChild(el);
        badges.set(id, { el: el, node: messageNode });
        schedule();
        return el;
      },
      removeBadge: function (messageId) {
        const rec = badges.get(messageId);
        if (rec) { rec.el.remove(); badges.delete(messageId); }
      },
      clear: function () {
        for (const [, rec] of badges) rec.el.remove();
        badges.clear();
      },
      /**
       * The persistent, non-dismissible scanning-state indicator. It is never
       * removed while the extension is active on this page - a user must always
       * be able to see whether they are actually being protected.
       */
      setStatus: function (state, text) {
        if (!statusEl) {
          statusEl = doc.createElement("div");
          statusEl.className = "status";
          layer.appendChild(statusEl);
        }
        statusEl.setAttribute("data-state", state);
        statusEl.textContent = text || state;
        statusEl.title = text || state;
      },
      reposition: schedule,
      badgeCount: function () { return badges.size; },
      destroy: function () {
        api.clear();
        if (raf !== null && typeof cancelAnimationFrame !== "undefined") cancelAnimationFrame(raf);
        host.remove();
      },
    };
    host.__phisherman = api;
    return api;
  }

  return { create: create, LAYER_ID: LAYER_ID, SEVERITY: SEVERITY, LABEL: LABEL };
});
