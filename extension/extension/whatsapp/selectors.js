/*
 * extension/whatsapp/selectors.js - VERSIONED selector registry.
 *
 * ZERO CLASS-NAME SELECTORS. WhatsApp Web's class names are build-hashed and
 * rotate without notice; a selector like `._21Ahp` is a time bomb that fails
 * silently on a Tuesday. Every selector here targets a ROLE, a DATA ATTRIBUTE or
 * a STRUCTURAL relationship - things that exist because the app needs them to
 * work, not because a bundler emitted them.
 *
 * Three tiers per target, tried in order. Tier 1 is the attribute we most want;
 * tier 3 is a structural fallback that should keep working even after a rewrite.
 * A target that only resolves at tier 3 is still a resolution, but health.js
 * counts tier depth so degradation is visible before it becomes blindness.
 *
 * THE ANCHOR: [data-pre-plain-text]. Its value is "[HH:MM, DD/MM/YYYY] Sender: "
 * - sender identity AND timestamp in one parse, on the element that also holds
 * the message body. It is set for the copy-to-clipboard feature, so it survives
 * styling rewrites. Everything else here is built around it.
 *
 * PURE MODULE: takes a root node, returns nodes. No chrome.*, no network.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaSelectors = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Bump when a tier is added, removed or reordered. Recorded in every verdict
  // so a field report can be traced to the registry that produced it.
  const REGISTRY_VERSION = "wa_sel_v1";

  // i18n "Forwarded" labels. WhatsApp localises this string; matching only the
  // English form would silently drop the flag for most Indian users.
  const FORWARDED_LABELS = [
    "forwarded", "forwarded many times",
    "अग्रेषित", "कई बार अग्रेषित",          // Hindi
    "अनेक वेळा अग्रेषित",                     // Marathi
    "ফরওয়ার্ড করা", "பகிரப்பட்டது", "ఫార్వార్డ్ చేయబడింది",
    "ಫಾರ್ವರ್ಡ್ ಮಾಡಲಾಗಿದೆ", "കൈമാറി", "ફૉરવર્ડ કરેલું",
    "reenviado", "transféré", "weitergeleitet",
  ];

  // System-message phrasings, used only to classify a row that has NO
  // data-pre-plain-text (system rows carry no sender). Matching is done on a
  // normalised, lowercased string and is intentionally loose.
  const SYSTEM_PHRASES = [
    "added you", "you were added", "created group", "created this group",
    "joined using this group's invite link", "changed the subject",
    "changed this group's icon", "messages and calls are end-to-end encrypted",
    "you're now an admin", "changed the group description",
    "disappearing messages were turned on", "security code changed",
    "आपको जोड़ा", "ने आपको जोड़ा",           // Hindi: "added you"
  ];

  /**
   * Each target: tiers[] of {name, find(root)}. `find` returns a node, a NodeList
   * or null. Tier order is significance order, never preference-by-brevity.
   */
  const TARGETS = {
    app_root: {
      expected: 1,
      tiers: [
        { name: "id#app", find: (d) => d.querySelector("#app") },
        { name: "role=application", find: (d) => d.querySelector('[role="application"]') },
        // Heuristic: the element that actually owns the two-pane layout.
        { name: "heuristic:widest-flex-container", find: (d) => {
            const cands = Array.from(d.querySelectorAll("div"))
              .filter((n) => n.children && n.children.length >= 2 && n.parentElement === d.body);
            return cands.length ? cands[0] : (d.body ? d.body.firstElementChild : null);
          } },
      ],
    },

    conversation: {
      expected: 1,
      tiers: [
        { name: "id#main", find: (d) => d.querySelector("#main") },
        // Structural: the pane that contains a composer AND a message list.
        { name: "structural:has-composer-and-rows", find: (d) => {
            const box = d.querySelector('[contenteditable="true"]');
            if (!box) return null;
            let n = box.parentElement;
            while (n && n !== d.body) {
              if (n.querySelector('[role="row"], [data-id]')) return n;
              n = n.parentElement;
            }
            return null;
          } },
        { name: "heuristic:tallest-scrollable", find: (d) => {
            let best = null, bestH = 0;
            for (const n of d.querySelectorAll("div")) {
              const h = n.scrollHeight || 0;
              if (h > bestH && h > (n.clientHeight || 0)) { best = n; bestH = h; }
            }
            return best;
          } },
      ],
    },

    scroll_container: {
      expected: 1,
      tiers: [
        { name: "role=application-inside-main", find: (d, main) =>
            (main || d).querySelector('[role="application"]') },
        { name: "parent-of-first-row", find: (d, main) => {
            const row = (main || d).querySelector('[role="row"], [data-id]');
            return row ? row.parentElement : null;
          } },
        { name: "heuristic:tallest-scrollable-in-main", find: (d, main) => {
            const scope = main || d;
            let best = null, bestH = 0;
            for (const n of scope.querySelectorAll("div")) {
              const h = n.scrollHeight || 0;
              if (h > bestH) { best = n; bestH = h; }
            }
            return best;
          } },
      ],
    },

    message_row: {
      expected: 1,           // "at least one"
      multi: true,
      tiers: [
        { name: "role=row", find: (d, scope) => (scope || d).querySelectorAll('[role="row"]') },
        { name: "data-id", find: (d, scope) => (scope || d).querySelectorAll("div[data-id]") },
        { name: "scroll-container-children", find: (d, scope) =>
            (scope || d) ? (scope || d).children : null },
      ],
    },

    // The anchor. Carries sender + timestamp + body in one node.
    message_meta: {
      expected: 1,
      multi: true,
      tiers: [
        { name: "data-pre-plain-text", find: (d, scope) =>
            (scope || d).querySelectorAll("[data-pre-plain-text]") },
        // copyable-text is a stable hook WhatsApp uses for clipboard support.
        { name: "copyable-text-ancestor", find: (d, scope) =>
            (scope || d).querySelectorAll('[data-testid="msg-container"], [class*="copyable-text"]') },
        { name: "first-text-node-of-row", find: (d, scope) =>
            (scope || d).querySelectorAll('[role="row"] span[dir="ltr"], [role="row"] span[dir="auto"]') },
      ],
    },

    chat_title: {
      expected: 1,
      tiers: [
        { name: "main-header-title-attr", find: (d, main) => {
            const h = (main || d).querySelector("header");
            return h ? h.querySelector("[title]") : null;
          } },
        { name: "header-span-dir-auto", find: (d, main) => {
            const h = (main || d).querySelector("header");
            return h ? h.querySelector('span[dir="auto"]') : null;
          } },
        { name: "document-title-fallback", find: (d) =>
            (d.title ? { getAttribute: () => d.title, textContent: d.title } : null) },
      ],
    },

    outgoing: {
      expected: 1,
      multi: true,
      tiers: [
        // data-id is "true_<chat>@c.us_<msgid>" for messages the user sent.
        { name: "data-id-prefix-true", find: (d, scope) =>
            (scope || d).querySelectorAll('[data-id^="true_"]') },
        { name: "aria-or-role-outgoing", find: (d, scope) =>
            (scope || d).querySelectorAll('[data-testid="msg-dblcheck"], [data-icon="msg-dblcheck"]') },
        { name: "position:right-aligned", find: (d, scope) => {
            const rows = (scope || d).querySelectorAll('[role="row"]');
            return Array.prototype.filter.call(rows, (r) => {
              const st = r.getAttribute && r.getAttribute("style") || "";
              return /flex-end|right/.test(st);
            });
          } },
      ],
    },

    forward_label: {
      expected: 0,           // absence is normal; never counted against health
      multi: true,
      optional: true,
      tiers: [
        { name: "data-icon=forward", find: (d, scope) =>
            (scope || d).querySelectorAll('[data-icon="forward"]') },
        { name: "i18n-forwarded-text", find: (d, scope) => {
            const out = [];
            for (const n of (scope || d).querySelectorAll("span")) {
              const t = (n.textContent || "").trim().toLowerCase();
              if (t && FORWARDED_LABELS.some((l) => t === l || t.indexOf(l) === 0)) out.push(n);
            }
            return out;
          } },
        { name: "aria-label-forwarded", find: (d, scope) =>
            (scope || d).querySelectorAll('[aria-label*="orward"]') },
      ],
    },

    system_message: {
      expected: 0,
      multi: true,
      optional: true,
      tiers: [
        { name: "row-without-pre-plain-text", find: (d, scope) => {
            const rows = (scope || d).querySelectorAll('[role="row"], div[data-id]');
            return Array.prototype.filter.call(rows, (r) =>
              !r.querySelector("[data-pre-plain-text]"));
          } },
        { name: "data-id-status-prefix", find: (d, scope) =>
            (scope || d).querySelectorAll('[data-id*="@g.us_"][data-id*="_system"]') },
        { name: "system-phrase-match", find: (d, scope) => {
            const out = [];
            for (const r of (scope || d).querySelectorAll('[role="row"], div[data-id]')) {
              const t = (r.textContent || "").trim().toLowerCase();
              if (t && SYSTEM_PHRASES.some((p) => t.indexOf(p) !== -1)) out.push(r);
            }
            return out;
          } },
      ],
    },
  };

  function _asArray(v) {
    if (!v) return [];
    if (v.nodeType) return [v];
    return Array.prototype.slice.call(v);
  }

  /**
   * Resolve one target. Returns {nodes, tier, tier_name, resolved}.
   * `tier` is 1-based; 0 means unresolved.
   */
  function resolve(targetName, doc, scope) {
    const target = TARGETS[targetName];
    if (!target) throw new Error("unknown selector target: " + targetName);
    for (let i = 0; i < target.tiers.length; i++) {
      let found;
      try { found = target.tiers[i].find(doc, scope); } catch (e) { found = null; }
      const nodes = _asArray(found);
      if (nodes.length) {
        return { nodes: nodes, tier: i + 1, tier_name: target.tiers[i].name,
                 resolved: true, target: targetName };
      }
    }
    return { nodes: [], tier: 0, tier_name: null, resolved: false, target: targetName };
  }

  return {
    REGISTRY_VERSION: REGISTRY_VERSION,
    TARGETS: TARGETS,
    FORWARDED_LABELS: FORWARDED_LABELS,
    SYSTEM_PHRASES: SYSTEM_PHRASES,
    resolve: resolve,
    targetNames: function () { return Object.keys(TARGETS); },
    requiredTargetNames: function () {
      return Object.keys(TARGETS).filter((k) => !TARGETS[k].optional);
    },
  };
});
