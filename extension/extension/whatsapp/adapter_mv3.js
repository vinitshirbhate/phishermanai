/*
 * extension/whatsapp/adapter_mv3.js - observers, budgets, lifecycle. THIN.
 *
 * The only file in whatsapp/ that touches the live DOM lifecycle or chrome.*.
 * selectors / health / extract / context / verdict are pure so they can be
 * exercised by eval/whatsapp_harness.js under Node against real captured DOM.
 * If you find yourself writing a scoring rule here, it belongs in verdict.js.
 *
 * THE RULE THIS FILE MOST HAS TO HONOUR: when health says BLIND, scanning STOPS
 * and the indicator says so. Scanning silently while unable to see is the worst
 * available outcome, because the user believes they are covered and they are
 * not. Every entry point below checks `may_scan` before doing anything.
 *
 * BUDGETS (measured, not asserted): <=8 ms per message, <=50 ms per batch,
 * <=200 messages retained per chat. Overruns are recorded and reported, not
 * silently absorbed.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.PhishermanWaAdapter = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const DEBOUNCE_MS = 150;
  const BACKFILL_LIMIT = 50;
  const MAX_RETAINED = 200;
  const BUDGET_MESSAGE_MS = 8;
  const BUDGET_BATCH_MS = 50;

  function now() {
    return (typeof performance !== "undefined" && performance.now) ? performance.now() : Date.now();
  }

  /**
   * start(deps) - deps are injected so this file holds no logic of its own:
   *   {document, selectors, health, extract, context, verdict, overlay,
   *    score(record, channel) -> verdict, isChatOptedOut(chatId) -> bool,
   *    onVerdict(verdict, node)}
   */
  function start(deps) {
    const d = deps.document;
    const SEL = deps.selectors, HEALTH = deps.health, EX = deps.extract;
    const OVERLAY = deps.overlay;

    let mo = null, io = null, healthTimer = null, debounce = null, overlay = null;
    let chatId = null, records = [], pending = new Set(), visible = new WeakSet();
    let lastHealth = null;
    const timings = { messages: [], batches: [], over_message_budget: 0, over_batch_budget: 0 };

    function _health() {
      const h = HEALTH.check(d);
      h.checked_at = new Date().toISOString();
      lastHealth = h;
      if (overlay) overlay.setStatus(h.state, h.copy.badge);
      if (!h.may_scan) stopObserving();          // BLIND: stop, and say so
      return h;
    }

    function _isRowShaped(node) {
      // WhatsApp mutates constantly for presence and typing indicators. Without
      // this filter the observer fires hundreds of times a second on nothing.
      if (!node || node.nodeType !== 1) return false;
      if (node.matches && (node.matches('[role="row"]') || node.matches("div[data-id]"))) return true;
      return !!(node.querySelector && node.querySelector("[data-pre-plain-text]"));
    }

    function _rowsIn(node) {
      if (_isRowShaped(node)) return [node];
      if (!node.querySelectorAll) return [];
      return Array.prototype.slice.call(node.querySelectorAll('[role="row"], div[data-id]'))
        .filter(_isRowShaped);
    }

    function processBatch() {
      debounce = null;
      if (!lastHealth || !lastHealth.may_scan) return;
      if (deps.isChatOptedOut && deps.isChatOptedOut(chatId)) return;

      const batchStart = now();
      const rows = Array.from(pending);
      pending.clear();

      for (const row of rows) {
        if (!row.isConnected) continue;
        // IntersectionObserver gate: only what the user can actually see.
        if (io && !visible.has(row)) continue;
        const t0 = now();
        let rec;
        try {
          rec = EX.fromRow(row, { chatId: chatId });
        } catch (e) {
          continue;                    // a malformed row must not kill the batch
        }
        // A deleted message keeps its record (with the flag) but loses its badge.
        if (rec.flags.is_deleted && rec.message_id && overlay) overlay.removeBadge(rec.message_id);

        // An edited message supersedes its own prior verdict rather than
        // accumulating a second one.
        const prior = records.findIndex((x) => x.message_id && x.message_id === rec.message_id);
        if (prior !== -1) records.splice(prior, 1);
        records.push(rec);
        if (records.length > MAX_RETAINED) records.splice(0, records.length - MAX_RETAINED);

        const channel = deps.context.assess(
          { chat_id: chatId, title: currentTitle(), member_count: currentMemberCount() },
          records, { seenHashes: deps.seenHashes });

        let v = null;
        if (!rec.flags.is_deleted) {
          try { v = deps.score(rec, channel); } catch (e) { v = null; }
        }
        const ms = now() - t0;
        timings.messages.push(Number(ms.toFixed(3)));
        if (ms > BUDGET_MESSAGE_MS) timings.over_message_budget++;

        if (v && v.badge && overlay) overlay.addBadge(row, v, deps.onBadgeClick);
        if (v && deps.onVerdict) deps.onVerdict(v, row);
      }

      const batchMs = now() - batchStart;
      timings.batches.push(Number(batchMs.toFixed(3)));
      if (batchMs > BUDGET_BATCH_MS) timings.over_batch_budget++;
    }

    function currentTitle() {
      const main = SEL.resolve("conversation", d).nodes[0];
      const t = SEL.resolve("chat_title", d, main).nodes[0];
      return t ? (t.getAttribute && t.getAttribute("title")) || t.textContent || null : null;
    }
    function currentMemberCount() {
      const main = SEL.resolve("conversation", d).nodes[0];
      const txt = main ? (main.textContent || "") : "";
      const m = /(\d[\d,]*)\s+members?/i.exec(txt);
      return m ? Number(m[1].replace(/,/g, "")) : null;
    }

    function stopObserving() {
      if (mo) { mo.disconnect(); mo = null; }
      if (io) { io.disconnect(); io = null; }
      pending.clear();
    }

    function openChat(newChatId) {
      stopObserving();
      chatId = newChatId;
      records = [];
      if (overlay) overlay.clear();

      const h = _health();
      const main = SEL.resolve("conversation", d).nodes[0];
      const scroll = main ? SEL.resolve("scroll_container", d, main).nodes[0] : null;
      if (!overlay && scroll) overlay = OVERLAY.create(d, scroll);
      if (overlay) overlay.setStatus(h.state, h.copy.badge);
      if (!h.may_scan || !scroll) return h;
      if (deps.isChatOptedOut && deps.isChatOptedOut(chatId)) {
        if (overlay) overlay.setStatus("OFF", HEALTH.COPY.OFF.badge);
        return h;
      }

      if (typeof IntersectionObserver !== "undefined") {
        io = new IntersectionObserver((entries) => {
          for (const e of entries) {
            if (e.isIntersecting) visible.add(e.target); else visible.delete(e.target);
          }
        }, { root: scroll, threshold: 0.01 });
      }

      // Backfill the last 50 VISIBLE messages, then stop. Deeper history is an
      // explicit user action, not something we do to every chat on open.
      const all = SEL.resolve("message_row", d, scroll).nodes;
      const tail = all.slice(Math.max(0, all.length - BACKFILL_LIMIT));
      for (const row of tail) { if (io) io.observe(row); visible.add(row); pending.add(row); }
      processBatch();

      mo = new MutationObserver((muts) => {
        for (const m of muts) {
          for (const n of m.addedNodes) for (const row of _rowsIn(n)) {
            if (io) io.observe(row);
            pending.add(row);
          }
          for (const n of m.removedNodes) {
            for (const row of _rowsIn(n)) {
              const id = row.getAttribute && row.getAttribute("data-id");
              if (id && overlay) overlay.removeBadge(id);
            }
          }
        }
        if (pending.size && debounce === null) debounce = setTimeout(processBatch, DEBOUNCE_MS);
      });
      // subtree + childList only. NOT attributes: WhatsApp rewrites attributes
      // constantly for presence and read receipts, and observing them would fire
      // continuously while telling us nothing about new messages.
      mo.observe(scroll, { childList: true, subtree: true });

      if (scroll && overlay) scroll.addEventListener("scroll", overlay.reposition, { passive: true });
      return h;
    }

    function scanThisChat() {
      if (!lastHealth || !lastHealth.may_scan) return null;
      const main = SEL.resolve("conversation", d).nodes[0];
      const scroll = main ? SEL.resolve("scroll_container", d, main).nodes[0] : null;
      if (!scroll) return null;
      for (const row of SEL.resolve("message_row", d, scroll).nodes) { visible.add(row); pending.add(row); }
      processBatch();
      return stats();
    }

    function optOut(id) {
      if (deps.setChatOptOut) deps.setChatOptOut(id || chatId, true);
      stopObserving();                                   // honoured immediately
      if (overlay) { overlay.clear(); overlay.setStatus("OFF", HEALTH.COPY.OFF.badge); }
    }

    function stats() {
      const msgs = timings.messages;
      const sorted = msgs.slice().sort((a, b) => a - b);
      const p = (q) => sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] : null;
      return {
        health: lastHealth,
        n_messages: msgs.length,
        per_message_ms: { p50: p(0.5), p95: p(0.95), max: sorted.length ? sorted[sorted.length - 1] : null },
        per_batch_ms: timings.batches.slice(-10),
        over_message_budget: timings.over_message_budget,
        over_batch_budget: timings.over_batch_budget,
        budget_message_ms: BUDGET_MESSAGE_MS,
        budget_batch_ms: BUDGET_BATCH_MS,
        retained: records.length,
        badges: overlay ? overlay.badgeCount() : 0,
      };
    }

    function closeChat() {
      stopObserving();
      if (healthTimer) { clearInterval(healthTimer); healthTimer = null; }
      if (overlay) overlay.clear();
    }

    /**
     * DELIVERABLE 8 / trigger T5 - message context for link verdicts.
     *
     * preflight/adapter_mv3.js exposes registerMessageContextProvider(fn); this
     * is the fn. Given an <a> inside a message row, it returns the chat context
     * that link arrived in, so a link in an unsolicited VIP-signals group is not
     * judged identically to the same link on a search-results page.
     *
     * Returns null when the anchor is not inside a readable message row, or when
     * health says we cannot see - never a fabricated context.
     */
    function messageContextForAnchor(anchorEl) {
      if (!lastHealth || !lastHealth.may_scan) return null;
      if (deps.isChatOptedOut && deps.isChatOptedOut(chatId)) return null;
      const row = anchorEl && anchorEl.closest
        ? anchorEl.closest('[role="row"], div[data-id]') : null;
      if (!row) return null;
      let rec = null;
      try { rec = EX.fromRow(row, { chatId: chatId }); } catch (e) { return null; }
      const channel = deps.context.assess(
        { chat_id: chatId, title: currentTitle(), member_count: currentMemberCount() },
        records, { seenHashes: deps.seenHashes });
      return {
        source: "whatsapp_lane",
        chat_id: chatId,
        message_id: rec.message_id,
        direction: rec.direction,
        is_forwarded: rec.flags.is_forwarded,
        forwarded_many_times: rec.flags.forwarded_many_times,
        channel_signals: channel.signals,
        // The exact shape securities_identity.py's T3 consumes.
        disclosure_channel_context: channel.disclosure_channel_context,
      };
    }

    healthTimer = setInterval(_health, HEALTH.RECHECK_MS);
    return { openChat, closeChat, scanThisChat, optOut, stats, health: _health,
             messageContextForAnchor: messageContextForAnchor,
             records: () => records.slice() };
  }

  return { start: start, DEBOUNCE_MS: DEBOUNCE_MS, BACKFILL_LIMIT: BACKFILL_LIMIT,
           MAX_RETAINED: MAX_RETAINED, BUDGET_MESSAGE_MS: BUDGET_MESSAGE_MS,
           BUDGET_BATCH_MS: BUDGET_BATCH_MS };
});
