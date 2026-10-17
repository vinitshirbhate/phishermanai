/* Shared toolbar-popup and side-panel tools. Network work stays in the worker. */
(() => {
  'use strict';
  let tab = null;
  let inputRevision = 0;
  let manualBusy = false;
  const el = id => document.getElementById(id);
  const send = request => chrome.runtime.sendMessage(request);
  const feedback = text => { el('workspace-feedback').textContent = text; };
  function append(parent, tag, text, className) {
    const node = document.createElement(tag); node.textContent = text;
    if (className) node.className = className;
    parent.append(node); return node;
  }
  function link(parent, label, value, base) {
    try {
      const url = new URL(value, base);
      if (!['http:', 'https:'].includes(url.protocol)) return;
      const anchor = append(parent, 'a', label, 'workspace-link');
      anchor.href = url.href; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer';
    } catch { /* Unusable third-party URLs are omitted. */ }
  }
  function renderFinancial(result) {
    const parent = el('financial-result'); parent.replaceChildren();
    el('financial-result-section').hidden = false;
    append(parent, 'strong', result.label || result.verdict, 'verification-label');
    append(parent, 'p', result.summary || 'No summary provided.');
    append(parent, 'p', result.scope || 'Selected-input result', 'muted-text');
    if (Number.isFinite(result.confidence)) append(parent, 'p', `Evidence availability: ${result.confidence}/100 · not a website trust score`, 'muted-text');
    const list = append(parent, 'ul', '', 'workspace-reasons');
    for (const reason of (result.reasons || []).slice(0, 12)) append(list, 'li', reason.message || reason.code);
    const filing = result.matched_filing;
    if (filing) {
      append(parent, 'h3', 'Matched filing');
      append(parent, 'p', [filing.company_name, filing.exchange, filing.filing_date].filter(Boolean).join(' · ') || 'No identified filing');
      if (filing.headline) append(parent, 'p', filing.headline);
      if (filing.pdf_url) link(parent, 'Open source filing', filing.pdf_url, result.endpoint);
    }
    for (const field of result.field_comparisons || []) {
      append(parent, 'p', `${field.field}: ${field.message || (field.match === true ? 'Matches the filing' : field.match === false ? 'Differs from the filing' : 'Could not compare')}`);
    }
    for (const action of result.recommended_actions || []) append(parent, 'p', [action.title, action.detail].filter(Boolean).join(' — '));
    if (result.warning_card_url) link(parent, 'Open warning card', result.warning_card_url, result.endpoint);
  }
  async function run(button, operation) {
    if (manualBusy) return;
    manualBusy = true; button.disabled = true;
    feedback('Checking…');
    try { await operation(); }
    catch (error) {
      feedback(error.message || 'Could not complete this check.');
      if (button.id === 'check-pdf') el('pdf-status').textContent = error.message || 'Could not check this PDF.';
    }
    finally { button.disabled = false; manualBusy = false; }
  }
  document.addEventListener('DOMContentLoaded', async () => {
    tab = await getActiveTab();
    el('open-side-panel').hidden = document.body.dataset.view !== 'popup';
    el('open-side-panel').onclick = () => {
      if (!tab?.id) { feedback('Open a browser tab first.'); return; }
      // Direct call retains the click's user gesture; do not await a worker round trip.
      chrome.sidePanel.open({ tabId: tab.id }).then(() => window.close()).catch(error => feedback(error.message));
    };
    el('workspace-settings').onclick = () => chrome.runtime.openOptionsPage();
    el('check-input').oninput = () => {
      inputRevision++;
      el('verify-consent').checked = false;
      el('input-local-result').hidden = true;
      el('financial-result-section').hidden = true;
    };
    el('use-selection').onclick = () => run(el('use-selection'), async () => {
      tab = await getActiveTab();
      if (!tab?.id || !/^https?:/.test(tab.url || '')) throw new Error('Select text on a normal website first.');
      const snapshot = await chrome.tabs.sendMessage(tab.id, { action: 'getSelectionContext' });
      const text = snapshot?.selection?.text;
      if (!text) throw new Error('Select the message or text on the page, then try again.');
      el('check-input').value = text.slice(0, 15000);
      el('check-input').dispatchEvent(new Event('input')); feedback('Selected text added. Choose a check below.');
    });
    el('check-input-local').onclick = () => run(el('check-input-local'), async () => {
      const revision = inputRevision;
      const result = await send({ action: 'quickCheckText', text: el('check-input').value });
      if (result.error) throw new Error(result.error);
      if (revision !== inputRevision) return;
      const parent = el('input-local-result'); parent.replaceChildren(); parent.hidden = false;
      append(parent, 'strong', result.riskLevel === 'SAFE' ? 'No strong local signals' : result.riskLevel);
      append(parent, 'p', result.coverage, 'muted-text');
      const list = append(parent, 'ul', '', 'workspace-reasons');
      for (const signal of result.signals || []) append(list, 'li', signal.label);
      for (const reason of result.securities?.reasons || []) append(list, 'li', reason.text);
      feedback('On-device check complete. No input was sent to a server.');
    });
    el('check-verifier').onclick = () => run(el('check-verifier'), async () => {
      const result = await send({ action: 'financialVerifierHealth' });
      if (result.error) throw new Error(result.error);
      el('verifier-status').textContent = result.message + (result.filings != null ? ` · ${result.filings.toLocaleString()} filings` : '');
      feedback(result.compatible ? 'Verifier status updated.' : result.message);
    });
    el('verify-input').onclick = () => run(el('verify-input'), async () => {
      if (!el('verify-consent').checked) throw new Error('Confirm sending only this input using the checkbox above.');
      const revision = inputRevision;
      const result = await send({ action: 'verifyFinancialInput', text: el('check-input').value, consent: true, tabId: tab?.id });
      if (result.error) throw new Error(result.error);
      if (revision !== inputRevision) return;
      renderFinancial(result); feedback('Financial verification complete.');
    });
    const settings = await send({ action: 'getSettings' });
    let pdfRevision = 0;
    el('pdf-file').onchange = () => { pdfRevision++; el('pdf-consent').checked = false; el('pdf-results').replaceChildren(); };
    el('check-pdf').onclick = () => run(el('check-pdf'), async () => {
      const revision = pdfRevision;
      const file = el('pdf-file').files[0];
      if (!file) throw new Error('Choose a PDF first.');
      if (file.size > 12 * 1024 * 1024) throw new Error('Use a PDF smaller than 12 MB.');
      if (!el('pdf-consent').checked) throw new Error('Confirm sending this PDF using the checkbox.');
      const current = await send({ action: 'getSettings' });
      if (!['local-server', 'remote'].includes(current.analysisMode)) throw new Error('Choose Local server mode in Settings to check PDFs.');
      const base = new URL(current.backendUrl);
      if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash) throw new Error('Invalid backend URL.');
      if (current.analysisMode === 'local-server' && !['127.0.0.1','localhost','[::1]'].includes(base.hostname)) throw new Error('Local server mode requires a loopback server.');
      const form = new FormData(); form.append('file', file);
      el('pdf-status').textContent = 'Reading PDF…';
      const response = await fetch(base.href.replace(/\/$/,'') + '/api/analyze/pdf', {method:'POST',body:form,credentials:'omit',redirect:'error',signal:AbortSignal.timeout(30000)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not check PDF. Restart the updated server on port 8000.');
      if (revision !== pdfRevision) return;
      const parent = el('pdf-results'); parent.replaceChildren();
      append(parent,'p',`${data.pages} pages · ${data.links.length} links found`);
      if (data.image_only) append(parent,'p','No readable text found. Scanned images need OCR; this check does not include it.');
      if (data.truncated) append(parent,'p','Some text or links exceeded the scan limit.');
      if (data.text.trim()) {
        const result = await send({action:'quickCheckText',text:data.text.slice(0,15000)});
        if (revision !== pdfRevision) return;
        append(parent,'p',result.error || (result.riskLevel === 'SAFE' ? 'Text: no strong local signals' : `Text: ${result.riskLevel}`));
        for (const signal of (result.signals || []).slice(0,3)) append(parent,'p',signal.label);
        if (data.text.length > 15000) append(parent,'p','Text check covers the first 15,000 characters.');
      }
      for (let index=0;index<data.links.length;index+=4) {
        const results = await Promise.all(data.links.slice(index,index+4).map(async item => ({item,result:await send({action:'preflightLink',url:item.url})})));
        if (revision !== pdfRevision) return;
        for (const {item,result} of results) {
          const row = append(parent,'div','', 'workspace-result');
          append(row,'strong',`Page ${item.page}: ${result.error ? 'Not checked' : result.verdict === 'L0_NO_SIGNALS' ? 'No obvious warning' : result.summary || result.verdict}`);
          append(row,'p',item.url,'muted-text');
        }
        el('pdf-status').textContent = `Checked ${Math.min(index+4,data.links.length)} of ${data.links.length} links…`;
      }
      el('pdf-status').textContent = 'PDF check complete. Link checks do not guarantee safety.';
      feedback('PDF checked.');
    });
    el('workspace-mode').textContent = ({local:'On-device checks', 'local-server':'Local server enhancement',remote:'Remote enhancement'})[settings.analysisMode] || 'On-device checks';
    el('verifier-status').textContent = `Financial verifier: ${settings.verifierUrl || 'http://127.0.0.1:8000'} · not contacted automatically`;
    if (tab?.id) { const last = await send({ action: 'getFinancialResult', tabId: tab.id }); if (last) renderFinancial(last); }
  });
  chrome.runtime.onMessage.addListener(message => {
    if (message.action === 'financialVerificationUpdated' && message.tabId === tab?.id && !manualBusy && !el('check-input').value) renderFinancial(message.result);
  });
  chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
    if (tabId !== tab?.id || !(changeInfo.url || changeInfo.status === 'loading')) return;
    inputRevision++;
    el('verify-consent').checked = false;
    el('financial-result-section').hidden = true;
    el('input-local-result').hidden = true;
  });
  chrome.tabs.onActivated.addListener(async () => {
    tab = await getActiveTab(); inputRevision++;
    el('check-input').value = ''; el('verify-consent').checked = false;
    el('financial-result-section').hidden = true; el('input-local-result').hidden = true;
    const last = await send({ action: 'getFinancialResult', tabId: tab?.id }); if (last) renderFinancial(last);
  });
})();
