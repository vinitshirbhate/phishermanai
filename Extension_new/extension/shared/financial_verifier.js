/* Selected-input verifier bridge. No automatic requests or text persistence. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.PhishermanFinancialVerifier = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  function redact(text) {
    return String(text || '')
      .replace(/(?<![\w@.])(?:\+?91[\s-]?)?[6-9]\d{9}(?![\w@])/g, '[phone redacted]')
      .replace(/\b[\w.+-]+@(?:[\w-]+\.)+[a-z]{2,}\b/gi, '[email redacted]');
  }
  function endpoint(settings) {
    const url = new URL(settings.verifierUrl || 'http://127.0.0.1:8000');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error('Use an HTTP or HTTPS verifier origin without credentials or query parameters.');
    }
    if (!['local-server', 'remote'].includes(settings.analysisMode)) {
      throw new Error('Financial verification needs Local server or Remote mode. Choose a mode in Settings.');
    }
    if (settings.analysisMode === 'local-server' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      throw new Error('Local server mode requires a loopback financial verifier.');
    }
    return url.href.replace(/\/$/, '');
  }
  function health(data) {
    if (!data || !Number.isInteger(data.filings) || data.filings < 0) {
      return { compatible: false, available: false, filings: null,
        message: 'This server is missing financial verification. Start the unified backend with uvicorn main:app --port 8000.' };
    }
    return { compatible: true, available: data.status === 'ok', filings: data.filings,
      entities: Number.isInteger(data.entities) ? data.entities : null,
      message: data.status === 'ok' ? 'Financial verifier ready' : 'Financial corpus is not ready' };
  }
  async function inspectHealth(settings, fetcher = fetch) {
    const base = endpoint(settings);
    const response = await fetcher(base + '/health', {
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(2500),
    });
    if (!response.ok) throw new Error('Verifier health check returned HTTP ' + response.status);
    return { ...health(await response.json()), endpoint: base };
  }
  async function verify(settings, text, consent, fetcher = fetch) {
    if (consent !== true) throw new Error('Confirm sending this selected input before verification.');
    if (!String(text || '').trim()) throw new Error('Paste a message, claim, or link first.');
    if (text.length > 15000) throw new Error('Use at most 15,000 characters per check.');
    const base = endpoint(settings);
    const status = await inspectHealth(settings, fetcher);
    if (!status.compatible) throw new Error(status.message + ' Change Financial verifier URL in Settings to the financial API, normally http://127.0.0.1:8000.');
    if (!status.available) throw new Error('The financial verifier is running, but its corpus is not ready. Build its database and retry.');
    const form = new FormData();
    form.append('text', redact(text));
    form.append('channel', 'EXTENSION');
    const response = await fetcher(base + '/verify', { method: 'POST', body: form,
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10000) });
    if (response.status === 404) throw new Error('This server has no POST /verify route. Start Extension_new/backend with uvicorn main:app --port 8000 and reload the extension.');
    if (!response.ok) throw new Error('Financial verifier returned HTTP ' + response.status);
    const data = await response.json();
    if (!data || typeof data.verdict !== 'string' || !Array.isArray(data.reasons)) {
      throw new Error('The endpoint returned an incompatible verification response.');
    }
    // Confidence describes evidence availability, and is never converted to trust.
    return { ...data, endpoint: base, scope: 'Only the selected input; phone/email redaction applied' };
  }
  return { redact, endpoint, health, inspectHealth, verify };
});
