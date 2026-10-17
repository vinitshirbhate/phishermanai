/* Personal preferences never alter evidence or raise trust scores. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.PhishermanUserPolicy = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const DAY = 86400000;
  function hostname(url) {
    try {
      const u = new URL(url);
      if (!['http:', 'https:'].includes(u.protocol)) return null;
      return u.hostname.toLowerCase().replace(/\.$/, '');
    } catch { return null; }
  }
  function eligible(assessment) {
    if (!assessment || assessment.messaging || assessment.suppressed) return false;
    if (assessment.riskLevel !== 'CAUTION') return false;
    // Unknown or strong findings remain visible. Only explicit weak evidence is eligible.
    const risks = (assessment.signals || []).filter(s => s.polarity === 'risk');
    return risks.length > 0 && risks.every(s => s.severity === 'low'
      && !/known|blocklist|mismatch|credential|registration|apk|impersonat|typosquat|otp|punycode|lookalike|sensitive.data|social.engineering|kyc|account.suspend/i.test(s.code + ' ' + s.label));
  }
  function apply(assessment, entries, now = Date.now()) {
    const host = hostname(assessment.url);
    const entry = entries[host];
    return { ...assessment, personalException: !!(entry && entry.expiresAt > now),
      quietWarning: !!(entry && entry.expiresAt > now && eligible(assessment)),
      canRemember: eligible(assessment) && !(entry && entry.expiresAt > now) };
  }
  function create(url, now = Date.now()) {
    const host = hostname(url);
    if (!host || ['github.io', 'vercel.app', 'onrender.com', 'gov.in', 'nic.in'].includes(host)) {
      throw new Error('Choose an exact website hostname, not a shared hosting suffix.');
    }
    return { hostname: host, createdAt: now, expiresAt: now + 30 * DAY };
  }
  return { hostname, eligible, apply, create };
});
