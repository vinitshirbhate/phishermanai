// Phisherman AI v6.1 - Background Service Worker
// Coordinates page analysis via backend, manages badge, caches results
// v6.1: Local gate (offline), persistent domain cache, WhatsApp scanning
// v7.0: Layer 1.6 offline securities registration quick-check (F-B1)

// Layer 1.6 - offline SEBI registration + @valid UPI quick-check.
// Layer 1.5a - offline LR-lex ML scorer (needs no DOM: works on hover + messages).
// Pre-flight  - offline link inspection (preflight/*).
//
// ORDER IS LOAD-BEARING. These modules use the UMD pattern: under Node they
// `require` their dependencies, but in the service worker `require` is
// undefined and they resolve from the global instead. A module must therefore
// be imported AFTER everything it depends on:
//   normalise + psl      -> url_parse
//   securities_check     -> preflight/identity
importScripts(
  'shared/normalise.js',
  'shared/signal_polarity.js',
  'shared/apk_check.js',
  'preflight/psl.js',
  // fetcher.js depends on url_parse.js, so it is imported after it below.
  'securities_check.js',
  'ml_scorer.js',
  'preflight/url_parse.js',
  'preflight/fetcher.js',
  'preflight/identity.js',
  'preflight/verdict.js',
  'preflight/adapter_mv3.js'
);

let _securitiesReady = false;
async function ensureSecuritiesSnapshot() {
  if (_securitiesReady) return true;
  try {
    const resp = await fetch(chrome.runtime.getURL('data/securities_snapshot.json'));
    self.PhishermanSecurities.load(await resp.json());
    _securitiesReady = true;
  } catch (e) {
    console.warn('Securities snapshot load failed:', e);
  }
  return _securitiesReady;
}
ensureSecuritiesSnapshot();

// --- Offline contact matching against the shipped anchors ---
//
// The snapshot carries salted one-way anchors for each registrant's e-mail
// and phone (see backend/engines/registry_schema.py and the `minimise()`
// docstring in scripts/fetch_sebi_register.py). They exist so this question
// -- "is this the address actually on SEBI's register for this
// registration?" -- can be answered on-device, with no network call and no
// readable directory of advisers' personal contact details in the bundle.
//
// The salt ships alongside the snapshot. It is not a secret from the user
// (it is on their own disk); its job is to stop a lifted bundle from being
// brute-forced against the 10-digit Indian mobile space offline, which an
// unsalted hash would permit trivially.
let _matchSalt = null;

async function ensureMatchSalt() {
  if (_matchSalt !== null) return _matchSalt;
  try {
    const resp = await fetch(chrome.runtime.getURL('data/securities_snapshot.json'));
    const snap = await resp.json();
    _matchSalt = (snap.meta && snap.meta.anchor_salt) || '';
  } catch (e) {
    _matchSalt = '';
  }
  return _matchSalt;
}

function normaliseEmailForMatch(v) {
  return String(v || '').trim().toLowerCase();
}

// Digits only, last 10. SEBI's own data is inconsistent -- the register
// carries values like "00007738942481" for a 10-digit Mumbai mobile -- so
// both sides are reduced to national significant digits before hashing, or
// the same number written two ways would fail to match itself.
function normalisePhoneForMatch(v) {
  const digits = String(v || '').replace(/\D/g, '');
  return digits.length >= 10 ? digits.slice(-10) : digits;
}

// The salt travels as hex but Python keys the HMAC with the RAW 32 bytes
// (`hmac.new(salt, ...)` where salt is bytes). Encoding the hex string as
// UTF-8 here would key with 64 different bytes and every anchor would
// mismatch -- silently, and in the "no" direction, so genuine registered
// contacts would be reported as not matching. Decode to bytes first.
function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(hex.substr(i * 2, 2), 16);
  }
  return out;
}

async function anchorValue(value, saltHex) {
  if (!value || !saltHex) return null;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw', hexToBytes(saltHex), { name: 'HMAC', hash: 'SHA-256' },
    false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(value));
  return [...new Uint8Array(sig)]
    .map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 32);
}

async function matchContactOffline(regNumber, observed, kind) {
  if (!(await ensureSecuritiesSnapshot())) return { match: 'unavailable' };
  const salt = await ensureMatchSalt();
  if (!salt) return { match: 'unavailable' };

  let rec = null;
  try {
    rec = self.PhishermanSecurities.lookup
      ? self.PhishermanSecurities.lookup(regNumber) : null;
  } catch (e) { rec = null; }
  if (!rec) return { match: 'unavailable' };

  const stored = kind === 'phone' ? rec.phone_hash : rec.email_hash;
  if (!stored) {
    return {
      match: 'unknown', kind, reg_number: regNumber,
      registered_name: rec.registered_name,
      reason: 'The register holds no value for this field, so there is nothing to compare against. This is not a finding about the entity.',
    };
  }
  const probe = kind === 'phone'
    ? normalisePhoneForMatch(observed) : normaliseEmailForMatch(observed);
  if (!probe) return { match: 'unknown', kind, reason: 'Nothing observed to check.' };

  const computed = await anchorValue(probe, salt);
  if (computed === stored) {
    return {
      match: 'yes', kind, reg_number: regNumber, source: 'offline_anchor',
      registered_name: rec.registered_name,
      reason: `This ${kind} matches the one on SEBI's register for ${regNumber}.`,
    };
  }
  return {
    match: 'no', kind, reg_number: regNumber, source: 'offline_anchor',
    registered_name: rec.registered_name,
    reason: `This ${kind} is not the one on SEBI's register for ${regNumber}. Registrants do use additional addresses and numbers, so treat this as a prompt to verify through a channel you chose, not as proof of impersonation.`,
  };
}

let _mlReady = false;
async function ensureMLModel() {
  if (_mlReady) return true;
  try {
    const resp = await fetch(chrome.runtime.getURL('models/lr_v1.json'));
    _mlReady = self.PhishermanML.load(await resp.json());
  } catch (e) {
    // Absent model is a supported state (F-D2 rollback): the chain still
    // returns a verdict from the remaining layers.
    console.warn('ML model unavailable, Layer 1.5a disabled:', e);
  }
  return _mlReady;
}
ensureMLModel();

/**
 * Layer 1.5a - URL-only lexical features, mirroring ml/features.py.
 * Kept minimal on purpose: only the features the shipped model actually uses.
 */
function mlFeaturesFromUrl(rawUrl) {
  const url = rawUrl || '';
  let host = '';
  try { host = new URL(url.includes('://') ? url : 'http://' + url).hostname || ''; } catch (e) {}
  const entropy = (s) => {
    if (!s) return 0;
    const counts = {};
    for (const ch of s) counts[ch] = (counts[ch] || 0) + 1;
    return -Object.values(counts).reduce((a, c) => a + (c / s.length) * Math.log2(c / s.length), 0);
  };
  const SENSITIVE = ['login', 'verify', 'otp', 'password', 'kyc', 'aadhaar', 'pan', 'cvv',
    'upi', 'bank', 'account', 'wallet', 'secure', 'update', 'confirm'];
  const low = url.toLowerCase();
  const q = url.includes('?') ? url.slice(url.indexOf('?') + 1) : '';
  // Mirrors ml/features.py: present-but-not-@valid => 1. Enforced by
  // tests/test_feature_parity.py, which fails on any divergence (NFR-10).
  const upiIds = url.match(/\b[a-z0-9.\-_]{2,}@[a-z][a-z0-9.]{1,}\b/gi) || [];
  const upiOutside = upiIds.length
    ? (upiIds.some((u) => u.toLowerCase().includes('@valid')) ? 0 : 1)
    : 0;
  // features.py builds its haystack as `${url}\n${text}` lowercased; text is
  // empty on the URL-only path. Token count uses [a-z0-9]+ exactly as Python does.
  const SECURITIES_LEXICON = ['sebi', 'nse', 'bse', 'demat', 'ipo', 'trading', 'portfolio',
    'mutual fund', 'stock', 'shares', 'broker', 'investment', 'returns', 'profit',
    'advisory', 'research analyst', 'fpi', 'block trade', 'allotment', 'securities'];
  const hay = (url + '\n').toLowerCase();
  const countOccurrences = (s, sub) => {
    let n = 0, i = 0;
    while ((i = s.indexOf(sub, i)) !== -1) { n++; i += sub.length; }
    return n;
  };
  const secHits = SECURITIES_LEXICON.reduce((a, t) => a + countOccurrences(hay, t), 0);
  const totalTokens = (hay.match(/[a-z0-9]+/g) || []).length || 1;
  const secDensity = Number((secHits / totalTokens).toFixed(4));

  // --- Artefact-free domain-string group (18) ------------------------------
  // Mirrors ml/features.py::domain_features EXACTLY. These are the only
  // features the shipped URL model consumes: scheme, www-prefix, path and query
  // are excluded because in PhiUSIIL all three are collection artefacts
  // (eval/corpus_audit.py). Defined inline rather than as a sibling function
  // because tests/test_feature_parity.py extracts this function's body alone.
  //
  // NOTHING here is rounded, deliberately: Python round() is banker's rounding
  // and JS toFixed() rounds half away from zero, so a ratio landing on a 5 in
  // the 5th decimal would diverge by 1e-4 and break the 1e-6 parity gate.
  const MULTI_LABEL_SUFFIXES = new Set(('co.in net.in org.in gen.in firm.in ind.in ac.in edu.in '
    + 'res.in gov.in nic.in mil.in co.uk org.uk me.uk ac.uk gov.uk net.uk sch.uk ltd.uk plc.uk '
    + 'com.au net.au org.au edu.au gov.au id.au co.jp or.jp ne.jp ac.jp go.jp '
    + 'com.br net.br org.br gov.br com.cn net.cn org.cn gov.cn edu.cn '
    + 'com.sg net.sg org.sg edu.sg gov.sg com.my net.my org.my edu.my gov.my '
    + 'com.hk com.tw com.mx com.tr com.ar com.pk com.bd com.np com.lk '
    + 'co.za org.za co.nz org.nz co.kr co.id co.th or.th '
    + 'com.ph com.vn com.sa com.eg com.ng com.gh com.kw com.qa '
    + 'co.il org.il com.ua com.pl com.ru').split(' '));
  const SUSPICIOUS_TLDS = new Set(['tk', 'ml', 'ga', 'cf', 'gq', 'top', 'xyz', 'buzz', 'click',
    'link', 'work', 'loan', 'download', 'review', 'country', 'stream', 'gdn', 'racing', 'win',
    'bid', 'party', 'trade', 'date', 'faith', 'science', 'cricket', 'accountant', 'men', 'rest',
    'fit', 'surf', 'monster', 'quest', 'cyou', 'icu', 'sbs']);
  const BRAND_TOKENS = ['paytm', 'phonepe', 'gpay', 'googlepay', 'bhim', 'upi', 'npci',
    'sbi', 'hdfc', 'icici', 'axis', 'kotak', 'yesbank', 'pnb', 'bob', 'canara',
    'zerodha', 'groww', 'upstox', 'angelone', 'angelbroking', 'sharekhan',
    'motilal', 'iifl', '5paisa', 'dhan', 'kite', 'smallcase',
    'nse', 'bse', 'sebi', 'nsdl', 'cdsl', 'cams', 'kfintech', 'amfi',
    'aadhaar', 'uidai', 'incometax', 'gst', 'epfo', 'irctc',
    'amazon', 'flipkart', 'netflix', 'whatsapp', 'instagram', 'facebook',
    'google', 'microsoft', 'apple', 'paypal'];
  const IP_RE = /^\d{1,3}(\.\d{1,3}){3}$/;
  const isVowel = (c) => c === 'a' || c === 'e' || c === 'i' || c === 'o' || c === 'u';
  const isLetter = (c) => (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
  const isDigit = (c) => c >= '0' && c <= '9';

  // `reg` = the www-stripped host, subdomains RETAINED (ml/features.py::domain_string).
  let reg = (host || '').toLowerCase().trim().replace(/^\.+|\.+$/g, '');
  if (reg.startsWith('www.')) reg = reg.slice(4);
  const regIsIp = !!reg && IP_RE.test(reg);
  // `registrable` = the registrable domain, used only for the domain_* features.
  let registrable = reg;
  if (reg && !regIsIp) {
    const parts = reg.split('.');
    if (parts.length > 2) {
      registrable = MULTI_LABEL_SUFFIXES.has(parts.slice(-2).join('.'))
        ? parts.slice(-3).join('.')
        : parts.slice(-2).join('.');
    }
  }
  const labels = reg ? reg.split('.').filter((p) => p) : [];
  const regLabels = registrable ? registrable.split('.').filter((p) => p) : [];
  const sld = (regIsIp || !regLabels.length) ? '' : regLabels[0];
  const tld = (regIsIp || !labels.length) ? '' : labels[labels.length - 1];
  let letterCount = 0, digitCount = 0, vowelCount = 0;
  for (const ch of reg) {
    if (isDigit(ch)) digitCount++;
    else if (isLetter(ch)) { letterCount++; if (isVowel(ch)) vowelCount++; }
  }
  // Runs of the SAME character of length >= 3 ('gooogle' -> 1).
  let repeatedRuns = 0;
  for (let i = 0; i < reg.length;) {
    let j = i;
    while (j < reg.length && reg[j] === reg[i]) j++;
    if (j - i >= 3) repeatedRuns++;
    i = j;
  }
  let consonantRun = 0, curRun = 0;
  for (const ch of sld) {
    curRun = (isLetter(ch) && !isVowel(ch)) ? curRun + 1 : 0;
    if (curRun > consonantRun) consonantRun = curRun;
  }

  return {
    url_length: url.length,
    url_entropy: Number(entropy(url).toFixed(4)),
    subdomain_count: host ? Math.max(0, host.split('.').length - 2) : 0,
    param_count: q ? (q.match(/=/g) || []).length : 0,
    has_ip_host: /^\d{1,3}(\.\d{1,3}){3}$/.test(host) ? 1 : 0,
    has_punycode: host.includes('xn--') ? 1 : 0,
    sensitive_keyword_count: SENSITIVE.filter((k) => low.includes(k)).length,
    upi_id_present: upiIds.length ? 1 : 0,
    upi_outside_valid_namespace: upiOutside,
    securities_keyword_density: secDensity,
    // Artefact-free domain group - the shipped model's actual inputs.
    host_len: reg.length,
    host_entropy: entropy(reg),
    label_count: labels.length,
    hyphens: (reg.match(/-/g) || []).length,
    digits: digitCount,
    digit_ratio: reg ? digitCount / reg.length : 0,
    vowel_ratio: letterCount ? vowelCount / letterCount : 0,
    longest_label: labels.reduce((m, p) => Math.max(m, p.length), 0),
    tld_len: tld.length,
    suspicious_tld: SUSPICIOUS_TLDS.has(tld) ? 1 : 0,
    has_ip: regIsIp ? 1 : 0,
    brand_token_count: BRAND_TOKENS.filter((b) => reg.includes(b)).length,
    domain_entropy: entropy(sld),
    domain_len: sld.length,
    repeated_char_runs: repeatedRuns,
    consonant_run_max: consonantRun,
    has_digit_letter_mix: ([...sld].some(isDigit) && [...sld].some(isLetter)) ? 1 : 0,
  };
}

async function scoreUrlML(url) {
  if (!(await ensureMLModel())) return null;
  return self.PhishermanML.score(mlFeaturesFromUrl(url));
}

const DEFAULT_SETTINGS = {
  backendUrl: 'http://127.0.0.1:8799',
  autoScan: true,
  submitGuard: true,
  overlayPosition: 'bottom-right',
  overlayAutoHide: 10000,
  linkHoverTooltips: true,
  // OFF by default (BL-6, local by default). Turning it on lets the worker
  // contact a shortener to learn where it lands - useful, but it is a network
  // request the user did not make, so it is their choice, not ours. Links
  // carrying one-time tokens are refused even when this is on.
  resolveRedirects: false
};

// ─── Cloud API endpoint ───────────────────────────────────────────────────
// Fallback layer 3. The origin is a legacy infrastructure host and is NOT part
// of the product name - keep it here as the single source of truth. Changing it
// also requires updating the matching host_permissions entry in manifest.json,
// or the fetch is blocked by MV3.
const CLOUD_API_ORIGIN = 'https://chetana.activemirror.ai';
const CLOUD_API = `${CLOUD_API_ORIGIN}/api/scan/full`;

const tabCache = new Map();
const autoScanTimers = new Map();
let backendOnline = false;
let settings = { ...DEFAULT_SETTINGS };

// ─── Persistent Domain Reputation Cache ───────────────────────────────────
// Survives service worker restarts. Key: hostname, value: {score, riskLevel, ts}
const DOMAIN_CACHE_KEY = 'phisherman_domain_cache';
const DOMAIN_CACHE_TTL = 24 * 60 * 60 * 1000; // 24h

async function getDomainCache() {
  const s = await chrome.storage.local.get(DOMAIN_CACHE_KEY);
  return s[DOMAIN_CACHE_KEY] || {};
}

async function setCachedDomain(hostname, result) {
  const cache = await getDomainCache();
  cache[hostname] = { ...result, ts: Date.now() };
  // Prune entries older than TTL (keep cache lean)
  for (const [k, v] of Object.entries(cache)) {
    if (Date.now() - v.ts > DOMAIN_CACHE_TTL) delete cache[k];
  }
  await chrome.storage.local.set({ [DOMAIN_CACHE_KEY]: cache });
}

async function getCachedDomain(hostname) {
  const cache = await getDomainCache();
  const entry = cache[hostname];
  if (!entry) return null;
  if (Date.now() - entry.ts > DOMAIN_CACHE_TTL) return null;
  return entry;
}

// ─── Content-varying surfaces ─────────────────────────────────────────────
// On WhatsApp Web, Telegram Web and similar, the hostname is CONSTANT while the
// content is entirely different from one conversation to the next. Domain
// reputation is meaningless there, and caching by hostname is actively harmful:
//
//   BUG THIS FIXES - every WhatsApp chat scored an identical 91 "SAFE".
//   The first scan cached a verdict for `web.whatsapp.com`, and because the
//   cache is consulted BEFORE the analysis chain, every later chat short-
//   circuited to that stored score. The message text was never looked at, so
//   the only signal ever shown was "Unverified domain: whatsapp.com".
//
// Any surface where one host serves unrelated user content belongs here.
const MESSAGING_HOSTS = /(?:^|\.)(?:web\.whatsapp\.com|web\.telegram\.org|messenger\.com|discord\.com|teams\.microsoft\.com)$/i;

function isMessagingSurface(snapshot) {
  if (snapshot?.messaging) return true;   // content script extracted messages
  try {
    return MESSAGING_HOSTS.test(new URL(snapshot?.url || '').hostname);
  } catch {
    return false;
  }
}

// ─── Local Gate (runs with NO backend) ────────────────────────────────────
// Pattern-matched rules for India scam detection.
// Returns same shape as backend response so callers are unaware.

const LOCAL_GATE_RULES = [
  // UPI / KYC urgency
  { re: /upi.{0,20}collect|collect.{0,20}request|kyc.{0,20}expir|aadhaar.{0,20}updat|pan.{0,20}block|account.{0,20}suspend/i,
    signal: 'UPI/KYC urgency trigger', score: -28 },
  // Digital arrest scam
  { re: /digital.{0,10}arrest|cbi.{0,20}notice|arrest.{0,10}warrant|customs.{0,20}seize|police.{0,20}case.{0,20}your/i,
    signal: 'Digital arrest scam pattern', score: -38 },
  // OTP theft
  { re: /(?:share|send|give|enter|tell).{0,30}otp|otp.{0,30}(?:share|send|give)|one.time.password/i,
    signal: 'OTP solicitation', score: -25 },
  // Investment / task scam
  { re: /guaranteed.{0,15}return|daily.{0,10}profit|(?:easy|simple).{0,15}earn|task.{0,15}earn.{0,15}(?:\$|₹|rs\.?)/i,
    signal: 'Investment/task scam pattern', score: -22 },
  // Lottery / prize
  { re: /kbc.{0,20}(?:winner|prize|lottery)|congratulation.{0,20}(?:won|winner|prize)|lucky.{0,10}draw.{0,10}winner/i,
    signal: 'Lottery/prize scam', score: -30 },
  // Loan fraud
  { re: /instant.{0,15}loan.{0,15}approv|loan.{0,15}without.{0,15}(?:cibil|documents|docs)|pre.approv.{0,15}loan/i,
    signal: 'Fake loan offer', score: -20 },
  // Suspicious URL shorteners / TLDs
  { re: /(?:bit\.ly|tinyurl|t\.me\/[^c]|cutt\.ly|rb\.gy|is\.gd|ow\.ly)/i,
    signal: 'URL shortener redirect', score: -12 },
  // Fake .gov typosquats (common in India scams)
  { re: /(?:gov-in|govin|\.gov\.com|india-gov|\.gov\.org)/i,
    signal: 'Fake government domain', score: -35 },
  // Electricity/gas urgency
  { re: /electricity.{0,20}(?:cut|disconnect|block|suspend)|power.{0,20}(?:cut|disconnect).{0,20}tonight/i,
    signal: 'Utility disconnection threat', score: -25 },
  // Courier / delivery (FedEx/DHL scam)
  { re: /(?:fedex|dhl|india.post|courier).{0,30}(?:held|seized|customs|pay.{0,15}fee|release)/i,
    signal: 'Courier impersonation', score: -22 },
  // QR redirect payment scams
  { re: /scan.{0,20}(?:qr|code).{0,20}(?:receive|credit|refund|payment)|qr.{0,20}(?:refund|collect|receive)/i,
    signal: 'QR code payment redirection', score: -28 },
  // Deepfake / video verification lure
  { re: /deepfake|ai.{0,10}video|video.{0,15}verify|video.{0,15}kyc|face.{0,15}verify|live.{0,10}video.{0,10}call/i,
    signal: 'Deepfake or video-verification lure', score: -18 },
  // WhatsApp / Telegram fraud recruitment
  { re: /whatsapp.{0,20}(?:job|part.?time|investment|trading|task)|telegram.{0,20}(?:group|channel|investment|signal|trading)/i,
    signal: 'Messaging-platform scam funnel', score: -22 },
  // Fake authority / regulator pressure
  { re: /ed.{0,15}notice|cbi.{0,15}summons|income.tax.{0,20}notice|rbi.{0,20}freeze|cyber.?cell.{0,20}case/i,
    signal: 'Government or regulator impersonation', score: -35 },
  // SIM / mobile block scam
  { re: /sim.{0,15}block|mobile.{0,15}number.{0,15}suspend|reactivate.{0,15}sim/i,
    signal: 'SIM or mobile service suspension scam', score: -20 },
  // Fake customer support or remote access
  { re: /anydesk|teamviewer|quicksupport|remote.{0,15}access|screen.{0,15}share/i,
    signal: 'Remote-access takeover attempt', score: -30 },
  // Advance fee / processing fee
  { re: /processing.{0,15}fee|registration.{0,15}fee|advance.{0,15}payment|required.{0,10}to.{0,10}release/i,
    signal: 'Advance-fee demand', score: -20 },
  // Crypto / betting / casino funnel
  { re: /crypto.{0,20}profit|casino|betting|slot.{0,10}win|signal.{0,15}group/i,
    signal: 'High-risk betting or crypto lure', score: -18 },
];

// ─── Trusted hosts (offline gate only) ────────────────────────────────────
// A small mirror of backend/data/domain_whitelist.json, used ONLY to suppress
// generic topic-word rules when the backend is unreachable. Absence from this
// list carries no penalty - the list exists to prevent false positives, never
// to create them. Matching is suffix-based on the registrable domain so
// subdomains (netbanking.hdfcbank.com) are covered, while a typosquat
// (hdfcbank.com.evil.tk) is not.
const TRUSTED_HOSTS = [
  'gov.in', 'nic.in', 'sebi.gov.in', 'rbi.org.in', 'irdai.gov.in',
  'nseindia.com', 'bseindia.com', 'nsdl.co.in', 'cdslindia.com', 'amfiindia.com',
  'npci.org.in', 'bhimupi.org.in',
  'sbi.co.in', 'onlinesbi.sbi', 'hdfcbank.com', 'icicibank.com', 'axisbank.com',
  'kotak.com', 'bankofbaroda.in', 'pnbindia.in', 'canarabank.com',
  'zerodha.com', 'groww.in', 'upstox.com', 'angelone.in', 'icicidirect.com',
  'google.com', 'google.co.in', 'youtube.com', 'wikipedia.org', 'microsoft.com',
  'apple.com', 'amazon.in', 'flipkart.com', 'linkedin.com', 'github.com',
  'paytm.com', 'phonepe.com', 'razorpay.com',
];

function isTrustedHost(rawUrl) {
  try {
    const host = new URL(rawUrl || '').hostname.toLowerCase();
    return TRUSTED_HOSTS.some(d => host === d || host.endsWith('.' + d));
  } catch {
    return false;
  }
}

// ─── Offline behavioural lane ─────────────────────────────────────────────
// Mirror of backend/engines/behavior_lane.py, kept deliberately small: the
// highest-value tactics only, so the extension reaches a comparable verdict with
// the backend down. The backend pack is the fuller one - when it answers, its
// result is used instead of this.
//
// Why this exists at all: the 18 LOCAL_GATE_RULES above match scam VOCABULARY.
// A task scam can avoid every one of those words and still be a scam, because
// what makes it one is the STRUCTURE - a specific payout attached to trivial
// work, a bonus that precedes a fee, a one-word reply that opens the channel.
const LOCAL_BEHAVIOR_TACTICS = [
  { id: 'reward_bait', label: 'Concrete money promise', weight: 22,
    re: /\bearn\s+(?:rs\.?|inr|₹)?\s*[\d,]+\s*(?:to|-|–)\s*(?:rs\.?|inr|₹)?\s*[\d,]+|\b(?:earn|income|salary|payout|profit)\s+(?:up\s+to\s+)?(?:rs\.?|inr|₹)\s*[\d,]{3,}|\b[\d,]{3,}\s*(?:rupees|rs\.?|inr|₹)\s*(?:per|a|every|\/)\s*(?:day|week|month|hour|task)\b|\b(?:daily|weekly|monthly)\s+(?:income|earning|earnings|payout|salary)\b|\b(?:salary|income)\s+[\d,]{4,}\b|\bearn\s+(?:up\s+to\s+)?[\d,]{3,}\b/i },
  { id: 'effort_reward_mismatch', label: 'Trivial task, large reward', weight: 24,
    re: /\b(?:give|post|leave|do|submit)\s+(?:us\s+)?(?:some\s+)?(?:positive|good|5[\s-]?star|five[\s-]?star)?\s*(?:ratings?|reviews?|likes?)\b|\b(?:rate|review|like|subscribe\s+to|follow)\s+(?:the\s+|our\s+|these\s+)?(?:brands?|products?|hotels?|videos?|apps?|channels?)\b|\bno\s+(?:experience|skill|skills|investment|qualification)\s+(?:is\s+)?(?:needed|required)\b|\b(?:just|simply|only)\s+(?:like|rate|review|click|watch|subscribe|share|forward)\b|\b(?:copy\s*[-–]?\s*paste|data\s+entry|form\s+filling|typing)\s+(?:job|work|task)\b|\b(?:easy|simple|basic)\s+(?:tasks?|work|job|online\s+work)\b/i },
  { id: 'reciprocity_hook', label: 'Free money before the ask', weight: 20,
    re: /\bjoining\s+(?:bonus|gift|reward|amount|credit)\b|\b(?:free|welcome|signup|sign[\s-]?up)\s+(?:bonus|credit|cash|reward)\b|\bfirst\s+(?:task|job|order)\s+(?:is\s+)?free\b/i },
  { id: 'commitment_ladder', label: 'Small first commitment', weight: 14,
    re: /\breply\s+(?:back\s+)?(?:with\s+)?["']?(?:yes|y|ok|okay|interested|start|1)["']?\b|\bif\s+(?:you\s+(?:are\s+)?)?interested\s*,?\s*(?:then\s+)?(?:reply|message|text|contact|dm|ping)\b/i },
  { id: 'unsolicited_recruitment', label: 'Unsolicited job offer', weight: 10,
    re: /\b(?:we|i)\s+(?:are|am)\s+(?:hiring|recruiting)\b|\b(?:part|full)[\s-]?time\s+(?:job|work|role|position)\b|\bwork\s*(?:ing)?\s+from\s+home\b|\bimmediate\s+joining\b/i },
  { id: 'trust_transfer', label: 'Borrowed brand trust', weight: 16,
    re: /\b(?:amazon|flipkart|meesho|myntra|zomato|swiggy|tata|reliance|google|microsoft|nykaa|ajio)\b.{0,40}\b(?:hiring|recruitment|project|campaign|partner|authoriz|authoris)|\bwe\s+work\s+(?:with|for)\s+(?:top\s+|leading\s+)?(?:brands?|companies|clients?)\b|\b(?:brands?|companies|clients?)\s+we\s+work\s+with\b/i },
  { id: 'advance_fee', label: 'Pay before you earn', weight: 28,
    re: /\b(?:registration|joining|training|security|processing|activation|refundable)\s+(?:fee|fees|charge|charges|deposit)\b|\b(?:pay|deposit|recharge|top[\s-]?up)\s+(?:rs\.?|₹)?\s*[\d,]+\s*(?:to|for)\s+(?:start|begin|activate|unlock|withdraw)\b|\bprepaid\s+task\b/i },
  { id: 'withdrawal_friction', label: 'Blocked withdrawal', weight: 30,
    re: /\bwithdraw(?:al|als)?\s+(?:is\s+|are\s+|has\s+been\s+)?(?:blocked|locked|frozen|on\s+hold|pending|restricted)\b|\b(?:pay|deposit|complete)\b.{0,40}\bto\s+(?:unlock|release|enable)\s+(?:your\s+)?(?:withdrawal|balance|funds?|earnings?)\b/i },
  { id: 'channel_migration', label: 'Move to a private channel', weight: 18,
    re: /\b(?:join|contact|message|add)\s+(?:me\s+|us\s+)?on\s+(?:telegram|whatsapp|signal)\b|\bt\.me\/|\bwa\.me\/|\b(?:download|install)\s+(?:our|the)\s+(?:app|apk)\b/i },
  { id: 'identity_probe', label: 'Early request for identity documents', weight: 30,
    re: /\b(?:send|share|provide|upload|give)\s+(?:me\s+|us\s+|your\s+)*(?:aadhaar|aadhar|pan\s*card|bank\s+(?:details|account)|passbook|selfie)\b|\b(?:otp|one[\s-]?time\s+password)\b.{0,30}\b(?:share|send|tell|provide|confirm)\b/i },
  { id: 'isolation_pressure', label: 'Told to keep it private', weight: 26,
    re: /\b(?:do\s*n[o']?t|never)\s+(?:tell|share|inform|discuss)\b.{0,30}\b(?:anyone|family|bank|police)\b|\bkeep\s+(?:this\s+)?(?:confidential|secret|between\s+us)\b/i },
];

const LOCAL_BEHAVIOR_COMBOS = [
  { id: 'task_scam_signature', requires: ['reward_bait', 'effort_reward_mismatch'], bonus: 22 },
  { id: 'recruitment_funnel', requires: ['unsolicited_recruitment', 'commitment_ladder'], bonus: 14 },
  { id: 'reciprocity_to_fee', requires: ['reciprocity_hook', 'advance_fee'], bonus: 24 },
  { id: 'invest_then_lock', requires: ['reward_bait', 'withdrawal_friction'], bonus: 28 },
  { id: 'lock_and_extract', requires: ['withdrawal_friction', 'advance_fee'], bonus: 26 },
  { id: 'brand_backed_pitch', requires: ['trust_transfer', 'reward_bait'], bonus: 16 },
  { id: 'credential_harvest', requires: ['unsolicited_recruitment', 'identity_probe'], bonus: 26 },
];

// Must match BAND_PENALTY_CAP / PENALTY_RATE in behavior_lane.py.
const LOCAL_BEHAVIOR_BANDS = [
  { min: 80, label: 'severe', cap: 65 },
  { min: 60, label: 'strong', cap: 50 },
  { min: 40, label: 'moderate', cap: 35 },
  { min: 20, label: 'weak', cap: 15 },
  { min: 0, label: 'none', cap: 10 },
];

function localBehaviorCheck(text) {
  const tactics = [];
  let total = 0;
  for (const t of LOCAL_BEHAVIOR_TACTICS) {
    const m = t.re.exec(text || '');
    if (!m) continue;
    tactics.push({ id: t.id, label: t.label, weight: t.weight, cue: m[0].replace(/\s+/g, ' ').slice(0, 100) });
    total += t.weight;
  }
  const hit = new Set(tactics.map(t => t.id));
  const combos = [];
  for (const c of LOCAL_BEHAVIOR_COMBOS) {
    if (c.requires.every(r => hit.has(r))) {
      combos.push({ id: c.id, requires: c.requires, bonus: c.bonus });
      total += c.bonus;
    }
  }
  const score = Math.max(0, Math.min(100, total));
  const band = LOCAL_BEHAVIOR_BANDS.find(b => score >= b.min) || LOCAL_BEHAVIOR_BANDS[LOCAL_BEHAVIOR_BANDS.length - 1];
  tactics.sort((a, b) => b.weight - a.weight);
  return {
    behaviorScore: score,
    band: band.label,
    tactics,
    combos,
    trustPenalty: Math.min(band.cap, Math.round(score * 0.65)),
    source: 'offline',
  };
}

function localGateCheck(payload) {
  const url = (payload.url || '').toLowerCase();
  // visibleText and messaging.text were missing here. The content script puts
  // page and message content in `visibleText`; omitting it meant the offline
  // gate often scored the TITLE alone and saw none of the actual content.
  const text = [
    payload.text,
    payload.title,
    payload.visibleText,
    payload.pageText,
    payload.messaging?.text,
    payload.selection?.text,
  ].filter(Boolean).join(' ');
  const combined = (url + ' ' + text).slice(0, 20000);

  const signals = [];
  let scoreDelta = 0;

  for (const rule of LOCAL_GATE_RULES) {
    if (rule.re.test(combined)) {
      signals.push(rule.signal);
      scoreDelta += rule.score;
    }
  }

  // Offline behavioural pass - mirrors backend/engines/behavior_lane.py so the
  // verdict does not collapse when the backend is unreachable. Same principle:
  // single tactics are weak, co-occurrence is the signal.
  const behavior = localBehaviorCheck(text);
  if (behavior.trustPenalty > 0) {
    scoreDelta -= behavior.trustPenalty;
    for (const t of behavior.tactics.slice(0, 4)) signals.push(`Behaviour: ${t.label}`);
  }

  // Suspicious TLD check on URL
  try {
    const hostname = new URL(payload.url || 'https://example.com').hostname;
    if (/\.(xyz|top|click|tk|ml|gq|cf|ga|pw|work|loan|racing)$/.test(hostname)) {
      signals.push('Suspicious domain TLD');
      scoreDelta -= 18;
    }
    if (/xn--/.test(hostname)) {
      signals.push('Punycode domain disguise');
      scoreDelta -= 20;
    }
    if (/(?:login|verify|update|secure|bonus|gift|claim|support|bank|kyc|upi|refund|help|telegram|whatsapp).{0,15}\.(?:xyz|top|click|shop|sbs|cfd|loan)/.test(hostname)) {
      signals.push('Phishing-style hostname pattern');
      scoreDelta -= 22;
    }
    // UPI ID patterns in text (qr code scams)
    if (/[a-z0-9.\-_]+@(?:okicici|okhdfcbank|okaxis|oksbi|paytm|upi|ybl|ibl|apl|aubank)/.test(text)) {
      // UPI ID present - neutral, but flag if combined with urgency
      if (scoreDelta < -15) {
        signals.push('UPI ID with urgency signals');
        scoreDelta -= 10;
      }
    }
  } catch {}

  if (/(?:click|tap).{0,15}(?:here|link).{0,15}(?:now|urgent)|limited.{0,10}time|act.{0,10}now|immediately/i.test(combined)) {
    signals.push('High-pressure action language');
    scoreDelta -= 12;
  }

  // Sensitive-data request. Two fixes over the original:
  //   1. Word boundaries - unanchored `pan` matched "ex-pan-d"/"com-pan-y" and
  //      `upi` matched "occ-upi-ed".
  //   2. Proximity - the term and the act had only to co-occur somewhere in
  //      20,000 characters, so a bank page mentioning "KYC" in one paragraph and
  //      "claim your reward points" in another scored -24. They must now appear
  //      within roughly one sentence of each other, in either order.
  const SENSITIVE = '(?:otp|upi|aadhaar|pan|cvv|mpin|bank account|net banking)';
  const DATA_ACT = '(?:verify|confirm|unlock|refund|claim|release|share|send|submit|update)';
  const proximity = new RegExp(
    `\\b${SENSITIVE}\\b.{0,40}\\b${DATA_ACT}\\b|\\b${DATA_ACT}\\b.{0,40}\\b${SENSITIVE}\\b`, 'i');
  // A bank telling you to update your KYC is the bank doing its job; the same
  // sentence from an unknown host is the phishing script. On a host we can
  // verify, this generic topic rule is suppressed - the specific scam-pattern
  // rules and the behavioural lane above still apply, so an actual scam hosted
  // on a trusted domain is not given a free pass.
  if (proximity.test(combined) && !isTrustedHost(payload.url)) {
    signals.push('Sensitive-data request with social engineering');
    scoreDelta -= 24;
  }

  const dedupedSignals = [...new Set(signals)];

  // Baseline 85, not 72. getRiskLevel() calls anything under 80 "CAUTION", so a
  // 72 baseline meant every page scanned with the backend down was flagged even
  // when it raised zero signals - an unconditional false positive in offline
  // mode. 85 puts a clean page in SAFE and leaves the rule deltas untouched.
  const trustScore = Math.max(0, Math.min(100, 85 + scoreDelta));
  return {
    trustScore,
    riskLevel: getRiskLevel(trustScore),
    signals: dedupedSignals,
    recommendations: signals.length > 0
      ? ['Do not share OTP or personal details', 'Verify via official channels only', 'Report to cybercrime.gov.in or call 1930']
      : [],
    behavior: behavior.behaviorScore > 0 ? behavior : null,
    source: 'local-gate',
    backendOnline: false,
  };
}

function isScannableUrl(url) {
  return Boolean(url && (url.startsWith('http://') || url.startsWith('https://')));
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function ensureContentScriptInjected(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ['content_script.js'],
    });
    return true;
  } catch {
    return false;
  }
}

async function requestSnapshot(tabId, retries = 4) {
  let lastError = null;
  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      const snapshot = await chrome.tabs.sendMessage(tabId, { action: 'snapshotPage' });
      if (snapshot && !snapshot.error) return snapshot;
      lastError = new Error(snapshot?.error || 'No snapshot returned');
    } catch (error) {
      lastError = error;
      if (attempt === 0) {
        await ensureContentScriptInjected(tabId);
      }
    }
    await wait(350 * (attempt + 1));
  }
  throw lastError || new Error('Could not access page content');
}

function scheduleAutoScan(tabId, delay = 700) {
  const existingTimer = autoScanTimers.get(tabId);
  if (existingTimer) clearTimeout(existingTimer);
  const timer = setTimeout(async () => {
    autoScanTimers.delete(tabId);
    try {
      await scanTab(tabId);
    } catch {}
  }, delay);
  autoScanTimers.set(tabId, timer);
}

// --- Badge Colors ---
const TRUST_COLORS = {
  SAFE:    { color: '#22c55e', range: [80, 100] },
  CAUTION: { color: '#eab308', range: [50, 79] },
  WARNING: { color: '#f97316', range: [25, 49] },
  DANGER:  { color: '#ef4444', range: [0, 24] }
};

function getRiskLevel(score) {
  if (score >= 80) return 'SAFE';
  if (score >= 50) return 'CAUTION';
  if (score >= 25) return 'WARNING';
  return 'DANGER';
}

function getBadgeColor(score) {
  const level = getRiskLevel(score);
  return TRUST_COLORS[level].color;
}

function normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function truncateText(text, maxLength = 220) {
  const normalized = normalizeText(text);
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function extractSignalLabel(signal) {
  if (typeof signal === 'string') return signal;
  return signal?.label || signal?.message || signal?.name || 'Signal detected';
}

function detectBehavioralTactics(text) {
  const source = normalizeText(text).toLowerCase();
  const matches = [];

  const rules = [
    {
      key: 'urgency',
      re: /\b(?:urgent|immediately|act now|within \d+ (?:minutes?|hours?)|limited time|hurry|today only|right now)\b/i,
      title: 'Urgency pressure',
      detail: 'The wording pushes fast action before the user has time to verify.',
      severity: 'high',
    },
    {
      key: 'authority',
      re: /\b(?:cbi|police|court|government|bank|rbi|official|legal notice|arrest warrant|cyber cell)\b/i,
      title: 'Authority leverage',
      detail: 'The message borrows institutional authority to increase compliance.',
      severity: 'high',
    },
    {
      key: 'reward',
      re: /\b(?:profit|earn|winner|prize|bonus|commission|returns?|refund|payout)\b/i,
      title: 'Reward bait',
      detail: 'The sender frames the interaction around easy gain, winnings, or recovery of money.',
      severity: 'medium',
    },
    {
      key: 'secrecy',
      re: /\b(?:do not tell|keep this private|confidential|only for you|don.?t share with anyone)\b/i,
      title: 'Isolation or secrecy',
      detail: 'The language tries to isolate the target from outside advice or verification.',
      severity: 'high',
    },
    {
      key: 'credential_theft',
      re: /\b(?:otp|verification code|upi pin|password|cvv|bank details|aadhaar|pan)\b/i,
      title: 'Credential harvesting',
      detail: 'The message focuses on collecting sensitive identifiers, codes, or financial credentials.',
      severity: 'high',
    },
    {
      key: 'compliance_path',
      re: /\b(?:click|tap|scan|download|install|join|send|share|pay)\b/i,
      title: 'Step-by-step compliance funnel',
      detail: 'The message tries to move the user through a concrete action path.',
      severity: 'medium',
    },
  ];

  for (const rule of rules) {
    const match = source.match(rule.re);
    if (!match) continue;
    matches.push({
      key: rule.key,
      title: rule.title,
      detail: rule.detail,
      severity: rule.severity,
      evidence: truncateText(match[0], 80),
    });
  }

  return matches;
}

function buildConversationInsights(snapshot) {
  const text = [
    snapshot.selection?.text,
    snapshot.selection?.surroundingText,
    snapshot.messaging?.text,
    snapshot.pageText,
  ].filter(Boolean).join('\n');

  const lines = text.split(/\n+/).map(line => normalizeText(line)).filter(Boolean);
  const linkCount = (text.match(/https?:\/\/|www\.|bit\.ly|tinyurl|t\.me\//gi) || []).length;
  const moneyMentions = (text.match(/\b(?:rs\.?|inr|rupees?|usd|\$|payment|refund|profit|commission|salary|earning)\b/gi) || []).length;
  const codeMentions = (text.match(/\b(?:otp|pin|cvv|verification code|password|mpin)\b/gi) || []).length;

  const observations = [];
  if (lines.length >= 3) observations.push(`The analysis looked across ${lines.length} message or text segments, not just the highlighted phrase.`);
  if (linkCount > 0) observations.push(`Link activity is present (${linkCount} link reference${linkCount === 1 ? '' : 's'}), which increases delivery risk.`);
  if (moneyMentions > 0) observations.push(`Financial language appears ${moneyMentions} time${moneyMentions === 1 ? '' : 's'}, suggesting money movement is part of the flow.`);
  if (codeMentions > 0) observations.push(`Sensitive-code language appears ${codeMentions} time${codeMentions === 1 ? '' : 's'}, which is common in takeover or payment scams.`);
  if (!observations.length) observations.push('No strong cross-message behavioral pattern was found beyond the direct selection and page context.');

  return {
    lineCount: lines.length,
    linkCount,
    moneyMentions,
    codeMentions,
    observations,
  };
}

function classifyQrValue(rawValue = '') {
  const value = String(rawValue || '');
  try {
    const parsed = new URL(value);
    return {
      type: parsed.protocol.startsWith('http') ? 'Web link' : parsed.protocol.replace(':', ''),
      host: parsed.hostname,
      note: parsed.protocol.startsWith('http')
        ? 'QR resolves to a clickable destination and should be verified before opening.'
        : 'QR contains a non-web URI payload.',
    };
  } catch {
    if (/@(?:okicici|okhdfcbank|okaxis|oksbi|paytm|upi|ybl|ibl|apl|aubank)\b/i.test(value)) {
      return {
        type: 'UPI/payment handle',
        host: '',
        note: 'Payment QR detected. Treat refund or receive-money claims with caution, since scan-to-receive scams are common.',
      };
    }
    return {
      type: 'Text payload',
      host: '',
      note: 'QR contains plain text or an unsupported payload.',
    };
  }
}

function buildMediaInsights(snapshot) {
  const images = Array.isArray(snapshot.media) ? snapshot.media : [];
  const qrCodes = Array.isArray(snapshot.qrCodes) ? snapshot.qrCodes : [];

  return {
    imageCount: images.length,
    qrCount: qrCodes.length,
    images: images.slice(0, 5).map((image) => ({
      title: truncateText(image.alt || image.caption || 'Visible image', 120),
      detail: truncateText(
        [image.caption, image.alt, image.srcHost ? `hosted on ${image.srcHost}` : '', image.width && image.height ? `${image.width}x${image.height}` : '']
          .filter(Boolean)
          .join(' • '),
        220
      ),
    })),
    qrCodes: qrCodes.slice(0, 4).map((qr) => {
      const classified = classifyQrValue(qr.rawValue);
      return {
        value: truncateText(qr.rawValue, 200),
        type: classified.type,
        host: classified.host || qr.host || '',
        note: classified.note,
        nearbyText: truncateText(qr.nearbyText || '', 180),
      };
    }),
  };
}

function buildDeepAnalysis(snapshot, result, assessment) {
  const combinedText = [
    snapshot.selection?.text,
    snapshot.selection?.surroundingText,
    snapshot.messaging?.text,
    snapshot.pageText,
  ].filter(Boolean).join('\n\n');

  // Merge the behaviour lane's tactics into the panel's existing behavioural
  // list. The backend pack is richer than the extension's local heuristics, so
  // its findings lead; local cues fill in behind them. Each carries the cue text
  // that triggered it so the user sees the evidence, not just a label.
  const lane = result?.behavior || null;
  const laneTactics = (lane?.tactics || []).map(t => ({
    title: t.label,
    detail: t.explain || '',
    severity: t.severity || 'medium',
    evidence: t.cue || '',
  }));
  const laneCombos = (lane?.combos || []).map(c => ({
    title: 'Reinforcing combination',
    detail: c.explain || `${(c.requires || []).join(' + ')} occur together.`,
    severity: 'high',
    evidence: '',
  }));
  const localTactics = detectBehavioralTactics(combinedText);
  const seen = new Set(laneTactics.map(t => t.title.toLowerCase()));
  const behavioral = [
    ...laneCombos,
    ...laneTactics,
    ...localTactics.filter(t => !seen.has(String(t.title || '').toLowerCase())),
  ];

  const conversation = buildConversationInsights(snapshot);
  const media = buildMediaInsights(snapshot);
  const topSignals = (assessment.signals || []).slice(0, 4).map(extractSignalLabel);

  const summaryParts = [];
  if (snapshot.selection?.text) {
    summaryParts.push(`The selected text was analyzed together with nearby context${snapshot.messaging?.messageCount ? ` and ${snapshot.messaging.messageCount} recent message(s)` : ' and broader page text'}.`);
  }
  if (lane?.narrative) {
    // The backend's plain-English read describes what the message DOES, which is
    // the part a score cannot convey.
    summaryParts.push(lane.narrative);
  } else if (behavioral.length > 0) {
    summaryParts.push(`Behaviorally, the strongest tactics look like ${behavioral.slice(0, 2).map(item => item.title.toLowerCase()).join(' and ')}.`);
  }
  if (media.qrCount > 0) {
    summaryParts.push(`A QR code was detected on the page${media.qrCodes[0]?.type ? ` with ${media.qrCodes[0].type.toLowerCase()} content` : ''}.`);
  } else if (media.imageCount > 0) {
    summaryParts.push(`Visible images were inventoried for supporting context, but no QR payload was decoded.`);
  }
  if (!summaryParts.length && topSignals.length > 0) {
    summaryParts.push(`Top risk signals: ${topSignals.slice(0, 2).join('; ')}.`);
  }

  return {
    summary: summaryParts.join(' '),
    selectedText: truncateText(snapshot.selection?.text || snapshot.visibleText || '', 500),
    surroundingText: truncateText(snapshot.selection?.surroundingText || '', 800),
    behavioral,
    behaviorScore: lane?.behavior_score ?? lane?.behaviorScore ?? null,
    behaviorBand: lane?.band || null,
    behaviorSource: lane ? (lane.source === 'offline' ? 'offline' : 'backend') : null,
    conversation,
    media,
  };
}

// --- Badge Update ---
async function updateBadge(tabId, score) {
  if (score === null || score === undefined) {
    await chrome.action.setBadgeText({ tabId, text: '' });
    return;
  }
  const text = String(Math.round(score));
  const color = getBadgeColor(score);
  await chrome.action.setBadgeText({ tabId, text });
  await chrome.action.setBadgeBackgroundColor({ tabId, color });
}

// --- Settings ---
async function loadSettings() {
  const stored = await chrome.storage.local.get('phisherman_settings');
  if (stored.phisherman_settings) {
    settings = { ...DEFAULT_SETTINGS, ...stored.phisherman_settings };
  }
  return settings;
}

async function saveSettings(newSettings) {
  settings = { ...DEFAULT_SETTINGS, ...newSettings };
  await chrome.storage.local.set({ phisherman_settings: settings });
  return settings;
}

// --- History ---
async function addToHistory(entry) {
  const stored = await chrome.storage.local.get('phisherman_history');
  const history = stored.phisherman_history || [];
  history.unshift({
    url: entry.url,
    title: entry.title,
    score: entry.trustScore,
    riskLevel: entry.riskLevel,
    timestamp: Date.now()
  });
  // Keep last 50
  if (history.length > 50) history.length = 50;
  await chrome.storage.local.set({ phisherman_history: history });
}

async function getHistory() {
  const stored = await chrome.storage.local.get('phisherman_history');
  return stored.phisherman_history || [];
}

async function clearHistory() {
  await chrome.storage.local.set({ phisherman_history: [] });
}

async function getFocusedPageTab() {
  const candidates = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const pageTab = candidates.find((tab) => tab.id && tab.url && /^https?:\/\//.test(tab.url));
  return pageTab || candidates[0] || null;
}

// --- Backend Communication ---
async function checkBackendHealth() {
  try {
    const resp = await fetch(`${settings.backendUrl}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    });
    backendOnline = resp.ok;
  } catch {
    backendOnline = false;
  }
  return backendOnline;
}

let cloudAvailable = true;

async function analyzeWithCloud(payload) {
  if (!cloudAvailable) return null;
  try {
    // Map extension snapshot to the cloud API format
    const body = {
      text: [payload.visibleText, payload.title, payload.url].filter(Boolean).join('\n').slice(0, 3000),
      lang: 'en',
      context: payload.messaging?.source || 'browser',
    };
    const resp = await fetch(CLOUD_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(12000)
    });
    if (!resp.ok) { cloudAvailable = false; return null; }
    const data = await resp.json();
    // Normalize to extension format
    const score = data.risk_score !== undefined ? (100 - data.risk_score) : 50;
    return {
      trustScore: score,
      riskLevel: getRiskLevel(score),
      signals: data.why_flagged || [],
      recommendations: data.action_eligibility === 'WARN'
        ? ['Do not share personal details', 'Verify through official channels', 'Report to 1930 or cybercrime.gov.in']
        : [],
      verdict: data.verdict,
      source: 'cloud',
    };
  } catch {
    cloudAvailable = false;
    return null;
  }
}

// Restore cloud availability periodically
setInterval(() => { cloudAvailable = true; }, 5 * 60 * 1000);

async function analyzeWithBackend(payload) {
  if (!backendOnline) {
    await checkBackendHealth();
    if (!backendOnline) return null;
  }
  try {
    const endpoint = payload.messaging ? '/api/scamgate/scan' : '/api/analyze/page';
    const body = payload.messaging
      ? {
          text: payload.messaging.text || payload.visibleText || payload.pageText || '',
          url: payload.url || '',
        }
      : {
          url: payload.url || '',
          title: payload.title || '',
          text: payload.visibleText || payload.pageText || '',
          signals: {
            hasPassword: Boolean(payload.signals?.hasPassword),
            hasEmail: Boolean(payload.signals?.hasEmail),
            hasCc: Boolean(payload.signals?.hasCreditCard),
            formActionHosts: payload.signals?.formActionHosts || [],
            visibleLinkHosts: payload.signals?.visibleLinkHosts || [],
            externalLinkCount: payload.signals?.externalLinkCount || 0,
          },
        };
    const resp = await fetch(`${settings.backendUrl}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(15000)
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    // Trust and risk run in OPPOSITE directions. The previous form put
    // `data.risk_score` into a ?? chain of trust scores and then, in the branch
    // for "only risk_score was returned", used it as the trust score unchanged -
    // so a response of risk 90 would have rendered as trust 90, i.e. SAFE, on a
    // page the backend had just called dangerous. Both live endpoints return
    // `trust_score`, so this never fired; it was a landmine waiting for any
    // endpoint that reported risk instead. Converted explicitly, never mixed.
    const clamp = (n) => Math.max(0, Math.min(100, Number(n)));
    let normalizedScore;
    if (data.trustScore !== undefined) normalizedScore = clamp(data.trustScore);
    else if (data.trust_score !== undefined) normalizedScore = clamp(data.trust_score);
    else if (data.risk_score !== undefined) normalizedScore = 100 - clamp(data.risk_score);
    else normalizedScore = 50;
    if (!Number.isFinite(normalizedScore)) normalizedScore = 50;
    const backendSignals = Array.isArray(data.signals) ? data.signals : [];
    // Severity comes from the signal, not from the page score. Deriving it from
    // normalizedScore stamped every signal on a DANGER page as high-severity -
    // including "Domain is on trusted whitelist", which is a TRUST signal in
    // engines/domain_intel.py and was rendered to the user as a red threat.
    const normalizedSignals = backendSignals.map(
      (signal) => PhishermanSignalPolarity.normalise(signal));
    return {
      trustScore: normalizedScore,
      riskLevel: data.riskLevel ?? data.risk_level ?? getRiskLevel(normalizedScore),
      signals: normalizedSignals,
      recommendations: data.recommendations || data.recommended_actions || [],
      factCheck: data.factCheck || data.fact_check || null,
      // Behavioural read of the text (tactics, combos, plain-English narrative).
      // /api/scamgate/scan returns it top-level; /api/analyze/page nests the same
      // object under the trust verdict. Both shapes are accepted.
      behavior: data.behavior || data.l0?.behavior || null,
      verdict: data.verdict || data.summary || '',
      source: 'backend',
      raw: data,
    };
  } catch {
    backendOnline = false;
    return null;
  }
}

/**
 * Merge on-device attachment findings into an assessment.
 *
 * WHY IT RUNS HERE, AFTER THE BACKEND ANSWERED
 * --------------------------------------------
 * A WhatsApp file bubble carries no message text, so it contributes nothing to
 * the text the backend scores. A chat whose only dangerous content was
 * "Spotify v9.1.36.1948 (Premium) Mod2.apk" therefore came back SAFE 94 - the
 * verdict was true about the text and silent about the file sitting above it.
 *
 * The filename is evidence the service worker can read without the network, so
 * this runs unconditionally: backend up, backend down, or local gate only. An
 * APK offer is exactly the case where the user is least likely to have a
 * working backend and most likely to act.
 *
 * The score is FLOORED, never raised: attachment findings can only make a
 * verdict more cautious. A high-severity offer caps trust into the DANGER band
 * because installing is irreversible in a way that reading a page is not.
 */
function applyAttachmentSignals(assessment, snapshot) {
  const found = Array.isArray(snapshot?.attachments) ? snapshot.attachments : [];
  if (!found.length) return assessment;

  const reports = found
    .map((a) => PhishermanApkCheck.inspect(a))
    .filter((r) => r && r.is_apk);
  if (!reports.length) return assessment;

  const worst = reports.some((r) => r.severity === 'high') ? 'high' : 'medium';
  const cap = worst === 'high' ? 20 : 45;

  const newSignals = [];
  for (const r of reports) newSignals.push(...r.signals);
  // De-duplicate: two modded APKs in one chat should not print the delivery
  // signal twice.
  const seen = new Set();
  const merged = [];
  for (const s of newSignals) {
    if (seen.has(s.label)) continue;
    seen.add(s.label);
    merged.push(s);
  }

  assessment.signals = merged.concat(assessment.signals || []);
  assessment.trustScore = Math.min(assessment.trustScore, cap);
  assessment.attachmentFindings = reports.map((r) => ({
    filename: r.evidence.filename,
    severity: r.severity,
    claims: r.claims,
    brand: r.brand,
    explanation: PhishermanApkCheck.explain(r),
  }));
  return assessment;
}

// ─── Link preflight ────────────────────────────────────────────────────────
//
// The preflight modules were imported by the service worker and proved loadable
// by tests, but NOTHING CALLED THEM: `initBackground()` in
// preflight/adapter_mv3.js has no caller, so triggers T1-T7 never fired and the
// hover path in the page showed only a hostname. Module-level reachability was
// green the whole time - the file was imported, so the guard was satisfied - and
// the lane still did nothing. Entry points are now asserted separately; see
// tests/test_module_reachability.py::test_declared_entry_points_are_invoked.
//
// This is the pipeline, called directly, with the results cached per URL.

const PREFLIGHT_CACHE = new Map();
const PREFLIGHT_CACHE_MAX = 300;
const PREFLIGHT_TTL_MS = 10 * 60 * 1000;

function preflightLocal(url, ctx) {
  const parsed = PhishermanUrlParse.parse(url, ctx || {});
  const identity = PhishermanPreflightIdentity.resolve(parsed, ctx || {});
  const verdict = PhishermanPreflightVerdict.assemble(parsed, identity, ctx || {});
  return { parsed, identity, verdict };
}

function _cacheGet(key) {
  const hit = PREFLIGHT_CACHE.get(key);
  if (!hit) return null;
  if (Date.now() - hit.ts > PREFLIGHT_TTL_MS) { PREFLIGHT_CACHE.delete(key); return null; }
  return hit.value;
}

function _cacheSet(key, value) {
  if (PREFLIGHT_CACHE.size >= PREFLIGHT_CACHE_MAX) {
    PREFLIGHT_CACHE.delete(PREFLIGHT_CACHE.keys().next().value);   // oldest out
  }
  PREFLIGHT_CACHE.set(key, { ts: Date.now(), value });
}

/**
 * Analyse a link. Two stages, deliberately separable:
 *
 *   stage "offline" - parse, identity, verdict. No network, sub-millisecond,
 *                     always runs. This is what a hover gets immediately.
 *   stage "resolve" - walk the redirect chain. Opt-in, refuses single-use
 *                     tokens outright, and is what turns a shortener from
 *                     "destination unknown" into a named host.
 */
async function preflightLink(url, opts) {
  const o = opts || {};
  // Backend state is part of the key: a result cached while the backend was
  // asleep says "blocklist lookup did not run", and replaying that for 10
  // minutes after it comes up would be a stale claim about our own coverage.
  const key = (o.resolve ? 'R' : 'L') + (backendOnline ? 'B' : '-') + '|' + url;
  const cached = _cacheGet(key);
  if (cached) return { ...cached, cached: true };

  let out;
  try {
    out = preflightLocal(url, { pageHost: o.pageHost });
  } catch (e) {
    return { error: 'Link could not be read.', url };
  }

  const result = {
    url,
    verdict: out.verdict.verdict,
    codes: out.verdict.codes || [],
    summary: out.verdict.summary || '',
    host: out.parsed.host_normalised,
    registrable_domain: out.parsed.registrable_domain,
    is_shortener: !!out.parsed.is_shortener,
    expansion_required: !!out.parsed.expansion_required,
    skip_prefetch: !!out.parsed.skip_prefetch,
    identity: out.identity,
    destination: null,
  };

  // Reputation from the LOCAL backend, when it happens to be running.
  //
  // The hover card kept reporting "no signals", which was true and useless -
  // most links are fine, and a card that says nothing 95% of the time teaches
  // people to ignore it the other 5%. The answer is not to invent concern; it is
  // to say what was checked. The backend holds ~800k blocklisted domains plus
  // whitelist/TLD/typosquat intelligence and can answer that in under a
  // millisecond once warm.
  //
  // Never triggers a health probe: hovering a link must not wake a sleeping
  // backend or stall the card. If it is not already known-online, we skip it and
  // the card renders the local analysis alone.
  if (backendOnline) {
    try {
      const rep = await fetch(`${settings.backendUrl}/api/link/inspect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
        signal: AbortSignal.timeout(1200),
      });
      if (rep.ok) result.reputation = await rep.json();
    } catch { /* the local verdict stands on its own */ }
  }

  // Resolution is opt-in AND gated by the module's own refusal rules.
  if (o.resolve && (out.parsed.is_shortener || out.parsed.expansion_required)) {
    const chain = await PhishermanFetcher.resolve(url, {
      enabled: true,
      pageHost: o.pageHost,
      now: () => Date.now(),
    });
    result.destination = {
      resolved: chain.resolved,
      refused: chain.refused,
      reason: chain.reason || null,
      truncated: !!chain.truncated,
      hops: (chain.hops || []).map((h) => ({
        host: h.host_normalised, scheme: h.scheme, status: h.status || null,
      })),
      final_host: chain.final ? chain.final.host_normalised : null,
      final_registrable: chain.final ? chain.final.registrable_domain : null,
      signals: chain.signals || [],
    };

    // The destination gets the SAME identity analysis as a directly-typed link.
    // A shortener that lands on an impostor is an impostor; resolving the hop
    // and then not re-checking it would be theatre.
    if (chain.final && chain.final.href && chain.final.href !== url) {
      try {
        const dest = preflightLocal(chain.final.href, { pageHost: o.pageHost });
        result.destination.verdict = dest.verdict.verdict;
        result.destination.codes = dest.verdict.codes || [];
        result.destination.summary = dest.verdict.summary || '';
        if (_verdictRank(dest.verdict.verdict) > _verdictRank(result.verdict)) {
          result.verdict = dest.verdict.verdict;
          result.escalated_by_destination = true;
        }
      } catch { /* the chain is still worth showing */ }
    }
  } else if (out.parsed.is_shortener || out.parsed.expansion_required) {
    result.destination = {
      resolved: false, refused: true,
      reason: out.parsed.skip_prefetch
        ? PhishermanFetcher.REFUSE.SINGLE_USE_TOKEN
        : PhishermanFetcher.REFUSE.DISABLED,
      hops: [], signals: [],
    };
  }

  _cacheSet(key, result);
  return result;
}

// Severity rank for comparing a link's own verdict with its destination's.
// Read from the verdict module rather than restated here: a hand-copied list
// silently mis-ranks the moment a code is renamed, and I got two of the six
// names wrong writing it out from memory. ORDER is most-severe-first.
function _verdictRank(v) {
  const order = (PhishermanPreflightVerdict && PhishermanPreflightVerdict.ORDER) || [];
  const i = order.indexOf(v);
  return i === -1 ? -1 : order.length - i;
}

// Wire the preflight adapter's background half. Until now this was imported and
// never initialised, so its T4 context-menu entry ("Check this link with
// Phisherman") did not exist in the shipped extension.
//
// T6/T7 inside initBackground are guarded by `if (chrome.webNavigation)` and
// stay dormant: `webNavigation` is not in manifest permissions. Adding it would
// enable post-hoc badging of redirect landings - worth doing, but it widens the
// permissions the user is asked to grant, so it is left as an explicit choice
// rather than slipped in here.
try {
  PhishermanPreflightAdapter.initBackground({
    runPipeline: (url, ctx) => preflightLink(url, {
      pageHost: (ctx && ctx.pageHost) || '',
      resolve: settings.resolveRedirects === true,
    }),
  });
} catch (e) {
  console.warn('[Phisherman AI] preflight adapter init failed:', e);
}

async function factCheckWithBackend(payload) {
  if (!backendOnline) {
    await checkBackendHealth();
    if (!backendOnline) return null;
  }
  try {
    const resp = await fetch(`${settings.backendUrl}/api/fact-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(20000)
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    backendOnline = false;
    return null;
  }
}

// --- Page Scanning ---
async function scanTab(tabId) {
  let snapshot;
  try {
    snapshot = await requestSnapshot(tabId);
  } catch (error) {
    const message = String(error?.message || '');
    if (/cannot access|cannot be scripted|chrome:|edge:|about:|restricted/i.test(message)) {
      return { error: 'This page is restricted and cannot be scanned by the extension' };
    }
    return { error: 'Could not access page content. Refresh the page and try again.' };
  }

  if (!snapshot || snapshot.error) {
    return { error: snapshot?.error || 'No snapshot returned' };
  }

  // The content script sets scannable:false when it is on a webmail host but
  // could not isolate the open message. Scoring anyway means scoring the inbox
  // list - other people's promotional subject lines - and attributing the result
  // to whatever message the user has open. That produced "Lottery/prize scam" on
  // a genuine internship email. No verdict is the correct output here.
  if (snapshot.scannable === false) {
    return {
      url: snapshot.url,
      title: snapshot.title,
      trustScore: 50,
      riskLevel: 'UNKNOWN',
      suppressed: true,
      scanScope: snapshot.scanScope || 'unisolated',
      signals: [],
      recommendations: [],
      verdict: 'Not scanned. This message could not be separated from the rest of the page, '
             + 'and scoring the whole page would judge it on other messages’ content.',
      timestamp: Date.now(),
      source: 'suppressed',
    };
  }

  // Check persistent domain cache first - EXCEPT on messaging surfaces, where
  // one hostname serves unrelated conversations and a cached score would be
  // returned for content it was never computed from.
  const messagingSurface = isMessagingSurface(snapshot);
  let cachedResult = null;
  if (!messagingSurface) {
    try {
      const hostname = new URL(snapshot.url).hostname;
      cachedResult = await getCachedDomain(hostname);
    } catch {}
  }

  // Fallback chain: cache -> Ollama -> cloud API -> local gate
  let result = cachedResult
    || await analyzeWithBackend(snapshot)
    || await analyzeWithCloud(snapshot)
    || localGateCheck(snapshot);

  const assessment = {
    url: snapshot.url,
    title: snapshot.title,
    trustScore: result.trustScore ?? result.trust_score ?? 50,
    riskLevel: result.riskLevel ?? result.risk_level ?? getRiskLevel(result.trustScore ?? result.trust_score ?? 50),
    signals: result.signals || [],
    recommendations: result.recommendations || [],
    isNewsArticle: snapshot.isNewsArticle || false,
    factCheck: result.factCheck || result.fact_check || null,
    timestamp: Date.now(),
    backendOnline: result.source !== 'local-gate',
    source: result.source || 'backend',
    messaging: snapshot.messaging || null,
    behavior: result.behavior || null,
    raw: result.raw || null,
  };

  applyAttachmentSignals(assessment, snapshot);

  // Ensure riskLevel is consistent with score
  assessment.riskLevel = getRiskLevel(assessment.trustScore);
  assessment.analysisDetails = buildDeepAnalysis(snapshot, result, assessment);

  // Persist to domain cache if backend answered (not local gate).
  // Never write from a messaging surface: that verdict describes ONE conversation,
  // and storing it under the hostname would poison every other chat on that host.
  if (!messagingSurface && assessment.backendOnline && assessment.trustScore !== 50) {
    try {
      const hostname = new URL(snapshot.url).hostname;
      await setCachedDomain(hostname, {
        trustScore: assessment.trustScore,
        riskLevel: assessment.riskLevel,
        signals: assessment.signals,
      });
    } catch {}
  }

  tabCache.set(tabId, assessment);
  await updateBadge(tabId, assessment.trustScore);
  await addToHistory(assessment);

  // Send overlay render to content script
  try {
    await chrome.tabs.sendMessage(tabId, {
      action: 'renderAssessment',
      assessment,
      settings
    });
  } catch {
    // Content script may not be ready
  }

  return assessment;
}

// --- Event Listeners ---

// Tab navigation: auto-scan if enabled
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== 'complete') return;
  if (!isScannableUrl(tab.url)) return;

  await loadSettings();
  if (settings.autoScan) {
    scheduleAutoScan(tabId, 700);
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  await loadSettings();
  if (!settings.autoScan) return;

  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || !isScannableUrl(tab.url)) return;

  const cachedAssessment = tabCache.get(tabId);
  if (!cachedAssessment || cachedAssessment.url !== tab.url) {
    scheduleAutoScan(tabId, 250);
  }
});

// Tab removal: cleanup cache
chrome.tabs.onRemoved.addListener((tabId) => {
  tabCache.delete(tabId);
  const existingTimer = autoScanTimers.get(tabId);
  if (existingTimer) {
    clearTimeout(existingTimer);
    autoScanTimers.delete(tabId);
  }
});

// Action click: open side panel
chrome.action.onClicked.addListener(async (tab) => {
  await chrome.sidePanel.open({ tabId: tab.id });
});

// Health check alarm
chrome.alarms.create('healthCheck', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'healthCheck') {
    await checkBackendHealth();
  }
});

// ─── Context Menu - "Check with Phisherman AI" ───────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'phisherman-check-selection',
    title: 'Check with Phisherman AI 🛡',
    contexts: ['selection', 'link', 'image'],
  });
  chrome.contextMenus.create({
    id: 'phisherman-check-page',
    title: 'Check this page - Phisherman AI 🛡',
    contexts: ['page'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;

  if (info.menuItemId === 'phisherman-check-selection' || info.menuItemId === 'phisherman-check-page') {
    let snapshot = null;

    if (info.menuItemId === 'phisherman-check-selection' && info.selectionText) {
      try {
        snapshot = await chrome.tabs.sendMessage(tab.id, {
          action: 'getSelectionContext',
          selectedText: info.selectionText,
        });
      } catch {}
    }

    if (!snapshot || snapshot.error) {
      const text = info.selectionText || info.linkUrl || info.srcUrl || '';
      const url = info.pageUrl || tab.url || '';
      snapshot = {
        url,
        title: tab.title || '',
        visibleText: text,
        pageText: text,
        signals: {},
        selection: text ? { text, surroundingText: '', contextType: 'manual' } : null,
        media: info.srcUrl ? [{
          alt: '',
          caption: '',
          srcHost: (() => {
            try {
              return new URL(info.srcUrl).hostname;
            } catch {
              return '';
            }
          })(),
        }] : [],
        qrCodes: [],
        messaging: text ? { source: 'context-menu', text, messageCount: 1 } : null,
      };
    }

    const result = await analyzeWithBackend(snapshot)
      || await analyzeWithCloud(snapshot)
      || localGateCheck(snapshot);

    const trustScore = result.trustScore ?? 50;
    const assessment = {
      url: snapshot.url || info.pageUrl || tab.url || '',
      title: snapshot.title || tab.title || '',
      trustScore,
      riskLevel: result.riskLevel ?? getRiskLevel(trustScore),
      signals: result.signals || [],
      recommendations: result.recommendations || [],
      source: result.source || 'local-gate',
      timestamp: Date.now(),
      backendOnline: result.source !== 'local-gate',
      contextScan: true,
      scannedText: (snapshot.selection?.text || snapshot.visibleText || '').slice(0, 200),
      messaging: snapshot.messaging || null,
      behavior: result.behavior || null,
      raw: result.raw || null,
    };
    assessment.analysisDetails = buildDeepAnalysis(snapshot, result, assessment);

    tabCache.set(tab.id, assessment);
    await updateBadge(tab.id, assessment.trustScore);

    // Push result to side panel
    try {
      await chrome.tabs.sendMessage(tab.id, { action: 'renderAssessment', assessment, settings });
    } catch {}

    // Open side panel to show result
    await chrome.sidePanel.open({ tabId: tab.id });
  }
});

// --- Message Handlers ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse);
  return true; // async response
});

async function handleMessage(message, sender) {
  await loadSettings();

  switch (message.action) {
    case 'snapshotPage': {
      // Forwarded from panel - snapshot comes from content script
      const tabId = message.tabId;
      if (!tabId) return { error: 'No tabId' };
      try {
        const snapshot = await chrome.tabs.sendMessage(tabId, { action: 'snapshotPage' });
        return snapshot;
      } catch {
        return { error: 'Could not reach content script' };
      }
    }

    case 'scanActiveTab': {
      let tabId = message.tabId;
      if (!tabId) {
        const tab = await getFocusedPageTab();
        if (!tab) return { error: 'No active tab' };
        tabId = tab.id;
      }
      return await scanTab(tabId);
    }

    case 'getLastScan': {
      let tabId = message.tabId;
      if (!tabId) {
        const tab = await getFocusedPageTab();
        if (!tab) return null;
        tabId = tab.id;
      }
      return tabCache.get(tabId) || null;
    }

    case 'mlScoreUrl': {
      // Layer 1.5a - no DOM required, so this serves link-hover and message URLs.
      const ml = await scoreUrlML(message.url || '');
      if (!ml) return { available: false, reason: 'model not loaded', layer: '1.5a' };
      ml.available = true;
      ml.routing = self.PhishermanML.route(ml.p_phishing, message.registrationState || 'not_applicable');
      return ml;
    }

    case 'liveVerifyOfficial': {
      // Explicit, user-clicked, rate-limited live cross-check against SEBI's
      // own site (backend/engines/official_gov_verify.py). Never triggered
      // automatically — this is a real network call to a government server,
      // gated the same way redirect-resolution is gated for preflightLink.
      if (!message.reg_number) return { error: 'reg_number required', checked: false, matched: false };
      if (!backendOnline && !(await checkBackendHealth())) {
        return { error: 'Local backend is not running — start it to use live verification.', checked: false, matched: false };
      }
      try {
        const resp = await fetch(`${settings.backendUrl}/api/verify/official`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reg_number: message.reg_number }),
          signal: AbortSignal.timeout(12000),   // live gov-site round trip, not a hover budget
        });
        if (!resp.ok) return { error: `backend returned ${resp.status}`, checked: false, matched: false };
        return await resp.json();
      } catch (e) {
        return { error: e && e.message ? e.message : 'live verify request failed', checked: false, matched: false };
      }
    }

    case 'commsVerify': {
      // "Did SEBI actually issue this?" — checks a cited circular or
      // press-release reference against the regulator's own published index.
      // Authenticates the MESSAGE; securitiesCheck authenticates the SENDER.
      // A fabricated circular passes every sender check we have, because it
      // never claims to come from a registered intermediary at all.
      if (!backendOnline && !(await checkBackendHealth())) {
        return { state: 'index_unavailable', trust_delta: 0, reasons: [{
          code: 'COMMS_BACKEND_OFFLINE',
          text: 'The local backend is not running, so a cited official reference could not be checked either way.',
        }] };
      }
      try {
        const resp = await fetch(`${settings.backendUrl}/api/comms/verify`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: message.text || '', body: message.body || null }),
          signal: AbortSignal.timeout(8000),
        });
        if (!resp.ok) return { state: 'index_unavailable', trust_delta: 0, reasons: [] };
        return await resp.json();
      } catch (e) {
        return { state: 'index_unavailable', trust_delta: 0, reasons: [] };
      }
    }

    case 'matchContact': {
      // Equality test against the salted anchors in the bundled snapshot.
      // Tries offline first: the anchors ship precisely so this question does
      // not require a network round trip.
      const observed = message.observed || '';
      const reg = (message.reg_number || '').toUpperCase();
      const kind = message.kind === 'phone' ? 'phone' : 'email';
      if (!observed || !reg) return { match: 'unknown', kind, reason: 'Nothing to compare.' };

      const offline = await matchContactOffline(reg, observed, kind);
      if (offline && offline.match !== 'unavailable') return offline;

      if (!backendOnline && !(await checkBackendHealth())) {
        return { match: 'unknown', kind, reason: 'No local data or backend available to compare against.' };
      }
      try {
        const resp = await fetch(`${settings.backendUrl}/api/registry/match-contact`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reg_number: reg, observed, kind }),
          signal: AbortSignal.timeout(6000),
        });
        if (!resp.ok) return { match: 'unknown', kind, reason: `backend returned ${resp.status}` };
        return await resp.json();
      } catch (e) {
        return { match: 'unknown', kind, reason: 'Contact match request failed.' };
      }
    }

    case 'provenanceInspect': {
      // C2PA Content Credentials for one media asset. Reports provenance
      // STATES, never a synthetic-origin verdict — see
      // backend/engines/provenance_lane.py and the blocked-claims gate.
      if (!backendOnline && !(await checkBackendHealth())) {
        return { state: 'unsupported', trust_delta: 0, error: 'backend offline',
                 reasons: [{ code: 'PROV_BACKEND_OFFLINE',
                             text: 'Provenance checking needs the local backend, which is not running.' }] };
      }
      try {
        const resp = await fetch(`${settings.backendUrl}/api/provenance/inspect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            data_b64: message.data_b64 || '',
            mime: message.mime || '',
            filename: message.filename || '',
          }),
          signal: AbortSignal.timeout(20000),   // media, not a hover budget
        });
        if (!resp.ok) return { state: 'unsupported', trust_delta: 0, error: `backend ${resp.status}`, reasons: [] };
        return await resp.json();
      } catch (e) {
        return { state: 'unsupported', trust_delta: 0, error: 'inspect failed', reasons: [] };
      }
    }

    case 'preflightLink': {
      // T1 hover / T4 context menu. The offline stage always runs; redirect
      // resolution only when the user has switched it on, and never for a link
      // carrying a one-time token (enforced inside preflight/fetcher.js, not
      // here, so the rule holds for every caller).
      return await preflightLink(message.url || '', {
        pageHost: message.pageHost || '',
        resolve: settings.resolveRedirects === true,
      });
    }

    case 'securitiesCheck': {
      // F-B1/F-B2: registration + @valid identity. Backend first (adds
      // cross-handle collision detection); offline quick-check as the floor.
      const text = message.text || '';
      const poster = message.handle || message.url || '';
      const pageDate = message.pageDate || null;
      if (backendOnline || (await checkBackendHealth())) {
        try {
          const resp = await fetch(`${settings.backendUrl}/api/securities/identity`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, url: message.url || '', handle: message.handle || '', page_date: pageDate }),
          });
          if (resp.ok) {
            const data = await resp.json();
            data.source = 'backend';
            return data;
          }
        } catch (e) { /* fall through to offline */ }
      }
      await ensureSecuritiesSnapshot();
      const offline = self.PhishermanSecurities.quickCheck(text, poster, pageDate);
      offline.source = 'offline_quickcheck';
      return offline;
    }

    case 'chatContextChanged': {
      // A single-page messaging app switched conversation. The cached
      // assessment was computed about the PREVIOUS chat, so it must be
      // dropped rather than re-rendered beside a different one. Leaving it
      // up is the failure mode where a reassuring "no signals" verdict from
      // a family thread sits on screen while a stranger's opening pitch
      // arrives underneath it.
      const tabId = sender?.tab?.id;
      if (tabId != null) tabCache.delete(tabId);
      try {
        chrome.runtime.sendMessage({
          action: 'panelClearAssessment',
          reason: 'chat_changed',
          chatTitle: message.chatTitle || '',
        });
      } catch (e) { /* no panel open */ }
      return { cleared: true };
    }

    case 'scanText': {
      // Scan arbitrary text (from WhatsApp observer, context menu, etc.)
      const snapshot = {
        url: message.url || '',
        title: message.title || message.source || 'text-scan',
        visibleText: message.text || '',
        pageText: message.text || '',
        signals: {},
        messaging: {
          source: message.source || 'text',
          text: message.text,
          messageCount: message.messageCount || 1,
          flaggedMessages: message.flaggedMessages || [],
          chatTitle: message.chatTitle || '',
        },
      };
      const result = await analyzeWithBackend(snapshot)
        || await analyzeWithCloud(snapshot)
        || localGateCheck(snapshot);
      const trustScore = result.trustScore ?? result.trust_score ?? 50;
      const assessment = {
        url: snapshot.url,
        title: message.title || snapshot.messaging.chatTitle || 'Message Scan',
        trustScore,
        riskLevel: result.riskLevel ?? result.risk_level ?? getRiskLevel(trustScore),
        signals: result.signals || [],
        recommendations: result.recommendations || [],
        source: result.source || 'local-gate',
        timestamp: Date.now(),
        backendOnline: result.source !== 'local-gate',
        messaging: snapshot.messaging,
        behavior: result.behavior || null,
        verdict: result.verdict || '',
        raw: result.raw || null,
      };
      assessment.analysisDetails = buildDeepAnalysis(snapshot, result, assessment);

      const tabId = sender?.tab?.id || message.tabId;
      if (tabId) {
        tabCache.set(tabId, assessment);
        await updateBadge(tabId, assessment.trustScore);
        await addToHistory(assessment);
      }

      return assessment;
    }

    case 'scanSelectionContext': {
      const snapshot = message.payload;
      if (!snapshot?.visibleText && !snapshot?.selection?.text) {
        return { error: 'No selected text payload received' };
      }

      const result = await analyzeWithBackend(snapshot)
        || await analyzeWithCloud(snapshot)
        || localGateCheck(snapshot);
      const trustScore = result.trustScore ?? result.trust_score ?? 50;
      const assessment = {
        url: snapshot.url || sender?.tab?.url || '',
        title: snapshot.title || sender?.tab?.title || 'Selection Scan',
        trustScore,
        riskLevel: result.riskLevel ?? result.risk_level ?? getRiskLevel(trustScore),
        signals: result.signals || [],
        recommendations: result.recommendations || [],
        source: result.source || 'local-gate',
        timestamp: Date.now(),
        backendOnline: result.source !== 'local-gate',
        contextScan: true,
        scannedText: (snapshot.selection?.text || snapshot.visibleText || '').slice(0, 200),
        messaging: snapshot.messaging || null,
        behavior: result.behavior || null,
        raw: result.raw || null,
      };
      assessment.analysisDetails = buildDeepAnalysis(snapshot, result, assessment);

      const tabId = sender?.tab?.id || message.tabId;
      if (tabId) {
        tabCache.set(tabId, assessment);
        await updateBadge(tabId, assessment.trustScore);
        await addToHistory(assessment);
        try {
          await chrome.tabs.sendMessage(tabId, {
            action: 'renderAssessment',
            assessment,
            settings,
          });
        } catch {}
        await chrome.sidePanel.open({ tabId }).catch(() => null);
      }

      return assessment;
    }

    case 'factCheck': {
      const result = await factCheckWithBackend(message.payload);
      return result;
    }

    case 'openSidePanel': {
      const tabId = sender?.tab?.id || message.tabId;
      if (!tabId) return { error: 'No tab available' };
      await chrome.sidePanel.open({ tabId });
      return { ok: true };
    }

    case 'getSettings': {
      return settings;
    }

    case 'saveSettings': {
      return await saveSettings(message.settings);
    }

    case 'getHistory': {
      return await getHistory();
    }

    case 'clearHistory': {
      await clearHistory();
      return { ok: true };
    }

    case 'getBackendStatus': {
      return { online: backendOnline };
    }

    case 'checkHealth': {
      const online = await checkBackendHealth();
      return { online };
    }

    default:
      return { error: 'Unknown action' };
  }
}

// --- Init ---
(async () => {
  await loadSettings();
  await checkBackendHealth();
  console.log('[Phisherman AI] Service worker initialized. Backend:', backendOnline ? 'online' : 'offline');
})();
