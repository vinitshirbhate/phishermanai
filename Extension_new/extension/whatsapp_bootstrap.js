/* Browser entry point; pure WhatsApp modules stay separate from chrome APIs. */
(function () {
  'use strict';
  let adapter = null, activeChat = null;
  let stopped = false, timer = null;
  function stop() { stopped = true; clearInterval(timer); adapter?.closeChat(); }
  function send(message) {
    if (stopped) return Promise.resolve(null);
    try {
      if (!chrome.runtime?.id) { stop(); return Promise.resolve(null); }
      return chrome.runtime.sendMessage(message).catch(() => {
        if (!chrome.runtime?.id) stop();
        return null;
      });
    } catch { stop(); return Promise.resolve(null); }
  }
  const optedOut = new Set();
  function chatKey() {
    const main = PhishermanWaSelectors.resolve('conversation', document).nodes[0];
    const title = main && PhishermanWaSelectors.resolve('chat_title', document, main).nodes[0];
    return title ? title.getAttribute('title') || title.textContent : null;
  }
  function score(record, channel) {
    const local = window.__phishermanLocalGate?.(record.body_text || '', record);
    const result = PhishermanWaVerdict.assemble(record, channel, {
      registration: window.PhishermanSecurities?.quickCheck(record.body_text || '', record.sender?.display_name || '', record.timestamp),
    });
    // Local patterns must not be misrepresented as a regulator-published typology.
    if (record.direction !== 'outgoing' && local?.signals?.length
        && ['W0_NO_SIGNALS', 'W1_UNSOLICITED_CONTEXT', 'W2_UNVERIFIED_ADVISORY'].includes(result.verdict)) {
      result.badge = true;
      result.verdict = 'W3_TYPOLOGY_MATCH';
      result.summary = local.signals[0];
      result.codes = [{ code: 'LOCAL_CHAT_PATTERN', summary: local.signals[0], truth: 'content' }];
    }
    return result;
  }
  function start() {
    if (stopped) return;
    adapter = PhishermanWaAdapter.start({ document,
      selectors: PhishermanWaSelectors, health: PhishermanWaHealth,
      extract: PhishermanWaExtract, context: PhishermanWaContext,
      verdict: PhishermanWaVerdict, overlay: PhishermanOverlay, score,
      isChatOptedOut: id => optedOut.has(id), setChatOptOut: id => optedOut.add(id),
      onBadgeClick: () => send({ action: 'openSidePanel' }),
    });
    window.__phishermanChatStats = () => adapter.stats();
    let lastSignature = '';
    const tick = () => {
      if (stopped || !chrome.runtime?.id) { stop(); return; }
      const key = chatKey();
      if (!key && activeChat) {
        activeChat = null; lastSignature = ''; adapter.openChat(null);
        send({ action: 'chatContextChanged', url: location.href });
      }
      if (key && key !== activeChat) {
        activeChat = key;
        adapter.openChat(key);
        send({ action: 'chatContextChanged', url: location.href, chatTitle: key });
      } else if (key && !adapter.stats().health?.may_scan) {
        adapter.openChat(key);
      }
      if (!key || !adapter.stats().health?.may_scan) return;
      const records = adapter.records().filter(r => r.direction !== 'outgoing' && !r.flags.is_deleted);
      const signature = key + '|' + JSON.stringify(records.slice(-8).map(r =>
        [r.message_id, r.body_sha256, r.attachment, r.flags.is_edited]));
      if (records.length && signature !== lastSignature) {
        lastSignature = signature;
        send({ action: 'scanSenderTab' });
      }
    };
    timer = setInterval(tick, 1000);
    tick();
    window.addEventListener('pagehide', stop, { once: true });
  }
  // Worker reads private bundled assets; no web-accessible resource exposure needed.
  send({ action: 'getSecuritiesSnapshot' })
    .then(data => { if (data) window.PhishermanSecurities?.load(data); })
    .catch(() => {}).finally(start);
})();
