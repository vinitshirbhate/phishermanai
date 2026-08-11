// Phisherman AI v6 - Side Panel Logic

const TRUST_COLORS = {
  SAFE: '#22c55e',
  CAUTION: '#eab308',
  WARNING: '#f97316',
  DANGER: '#ef4444'
};

const RING_CIRCUMFERENCE = 2 * Math.PI * 52; // ~326.73

let currentAssessment = null;

// --- Helpers ---

function getRiskLevel(score) {
  if (score >= 80) return 'SAFE';
  if (score >= 50) return 'CAUTION';
  if (score >= 25) return 'WARNING';
  return 'DANGER';
}

function getColor(score) {
  return TRUST_COLORS[getRiskLevel(score)];
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

// A signal's severity is a property of the signal, never of the page verdict.
// This function used to read `assessment.riskLevel`, which meant every signal on
// a DANGER page rendered high-severity red - "Domain is on trusted whitelist"
// included, a +30 TRUST signal shown to the user as a threat. See
// shared/signal_polarity.js. `assessment` is retained so callers need no change.
function normalizeSignal(signal, assessment) {  // eslint-disable-line no-unused-vars
  return PhishermanSignalPolarity.normalise(signal);
}

function timeAgo(ts) {
  const diff = Date.now() - ts;
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

async function sendMsg(msg) {
  return chrome.runtime.sendMessage(msg);
}

function truncateText(text, maxLength = 220) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

async function getActiveTab() {
  const candidates = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  const pageTab = candidates.find((tab) => tab.id && tab.url && /^https?:\/\//.test(tab.url));
  return pageTab || candidates[0] || null;
}

// --- Rendering ---

function renderTrustScore(score) {
  const el = document.getElementById('trust-score');
  const ring = document.getElementById('ring-fill');
  const color = getColor(score);

  el.textContent = Math.round(score);
  el.style.color = color;

  const offset = RING_CIRCUMFERENCE * (1 - score / 100);
  ring.style.strokeDashoffset = offset;
  ring.style.stroke = color;
}

function renderRiskBadge(level) {
  const badge = document.getElementById('risk-badge');
  badge.textContent = level;
  badge.className = 'risk-badge ' + level.toLowerCase();
}

// Is the current page a messaging client, where "the page" and "the content"
// are entirely different things?
function isMessagingHost(url) {
  return /web\.whatsapp\.com|web\.telegram\.org|messenger\.com|discord\.com\/channels/
    .test(url || '');
}

// On WhatsApp Web the host page is Meta's, served over TLS, on a domain with
// impeccable reputation - so the page score is 100/SAFE and always will be,
// no matter what is being said in the conversation. Rendering that number
// unqualified next to a live scam is the single most misleading thing this
// panel can do: the user reads "SAFE" as a verdict on the message they are
// looking at, because that is what is in front of them.
//
// The score is not wrong, it is answering a different question. So say which
// question it answered.
function renderScoreScope(url) {
  const el = document.getElementById('score-scope');
  if (!el) return;
  if (isMessagingHost(url)) {
    el.textContent = 'This rates the website, not the conversation. '
      + 'Messages are assessed separately as they arrive.';
    el.style.display = 'block';
  } else {
    el.textContent = '';
    el.style.display = 'none';
  }
}

function renderPageInfo(title, url) {
  document.getElementById('page-title').textContent = title || 'Unknown Page';
  document.getElementById('page-url').textContent = url || '';
}

function renderSignals(signals, assessment = null) {
  const section = document.getElementById('signals-section');
  const list = document.getElementById('signal-list');

  if (!signals || signals.length === 0) {
    section.style.display = 'none';
    return;
  }

  // Risks first, most severe first; protective facts last and visibly distinct.
  // Ordering matters as much as colour: a protective signal listed among threats
  // reads as a threat however it is styled.
  const parts = PhishermanSignalPolarity.partition(signals);
  const ordered = parts.risk.concat(parts.context, parts.protective);
  section.style.display = 'block';

  const RISK_ICONS = { high: '\u26d4', medium: '\u26a0\ufe0f', low: '\u26a1' };
  list.innerHTML = ordered.map(s => {
    const icon = s.polarity === 'protective' ? '\u2713'
      : s.polarity === 'context' ? '\u2139\ufe0f'
        : (RISK_ICONS[s.severity] || '\u26a1');
    const cls = s.polarity === 'risk' ? `signal-severity-${s.severity}` : `signal-polarity-${s.polarity}`;
    return `
      <div class="signal-item ${cls}">
        <span class="signal-icon">${icon}</span>
        <span class="signal-text">${escapeHtml(s.label)}</span>
      </div>
    `;
  }).join('');
}

function renderFactCheck(factCheck, isNewsArticle) {
  const section = document.getElementById('factcheck-section');
  const content = document.getElementById('factcheck-content');

  if (!isNewsArticle || !factCheck) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';

  const credibility = factCheck.sourceCredibility ?? factCheck.source_credibility ?? '--';
  const claimCount = factCheck.claimCount ?? factCheck.claim_count ?? 0;
  const verified = factCheck.verifiedClaims ?? factCheck.verified_claims ?? 0;
  const unverified = factCheck.unverifiedClaims ?? factCheck.unverified_claims ?? 0;
  const claims = factCheck.claims || [];

  let html = `
    <div class="factcheck-grid">
      <div class="factcheck-stat">
        <div class="factcheck-stat-value" style="color: ${getColor(typeof credibility === 'number' ? credibility : 50)}">${credibility}</div>
        <div class="factcheck-stat-label">Source Credibility</div>
      </div>
      <div class="factcheck-stat">
        <div class="factcheck-stat-value" style="color: #e2e8f0">${claimCount}</div>
        <div class="factcheck-stat-label">Claims Found</div>
      </div>
      <div class="factcheck-stat">
        <div class="factcheck-stat-value" style="color: #22c55e">${verified}</div>
        <div class="factcheck-stat-label">Verified</div>
      </div>
      <div class="factcheck-stat">
        <div class="factcheck-stat-value" style="color: #f97316">${unverified}</div>
        <div class="factcheck-stat-label">Unverified</div>
      </div>
    </div>
  `;

  if (claims.length > 0) {
    html += claims.slice(0, 5).map(c => `
      <div class="claim-item">
        <span class="${c.verified ? 'claim-verified' : 'claim-unverified'}">
          ${c.verified ? '\u2713' : '\u2717'}
        </span>
        ${escapeHtml(c.text || c.claim || '')}
      </div>
    `).join('');
  }

  content.innerHTML = html;
}

function renderRecommendations(recommendations) {
  const section = document.getElementById('recommendations-section');
  const list = document.getElementById('recommendations-list');

  if (!recommendations || recommendations.length === 0) {
    section.style.display = 'none';
    return;
  }

  section.style.display = 'block';
  list.innerHTML = recommendations.map(r => {
    const text = typeof r === 'string' ? r : (r.text || r.message || '');
    return `<li><span class="rec-icon">\u2192</span> ${escapeHtml(text)}</li>`;
  }).join('');
}

function renderDeepAnalysis(details) {
  const summarySection = document.getElementById('summary-section');
  const behaviorSection = document.getElementById('behavior-section');
  const conversationSection = document.getElementById('conversation-section');
  const mediaSection = document.getElementById('media-section');

  if (!details) {
    summarySection.style.display = 'none';
    behaviorSection.style.display = 'none';
    conversationSection.style.display = 'none';
    mediaSection.style.display = 'none';
    return;
  }

  const summaryEl = document.getElementById('analysis-summary');
  const selectedBlock = document.getElementById('selection-evidence');
  const selectedText = document.getElementById('selected-text');
  const surroundingBlock = document.getElementById('surrounding-evidence');
  const surroundingText = document.getElementById('surrounding-text');
  const behaviorList = document.getElementById('behavior-list');
  const conversationStats = document.getElementById('conversation-stats');
  const conversationList = document.getElementById('conversation-list');
  const mediaList = document.getElementById('media-list');

  summaryEl.textContent = details.summary || 'No deeper context was captured for this scan.';
  if (details.selectedText) {
    selectedBlock.style.display = 'block';
    selectedText.textContent = details.selectedText;
  } else {
    selectedBlock.style.display = 'none';
  }

  if (details.surroundingText) {
    surroundingBlock.style.display = 'block';
    surroundingText.textContent = details.surroundingText;
  } else {
    surroundingBlock.style.display = 'none';
  }
  summarySection.style.display = 'block';

  const behavioral = details.behavioral || [];
  if (behavioral.length > 0) {
    behaviorSection.style.display = 'block';
    // Band header: tells the user how much weight the behavioural read carries,
    // and whether it came from the backend pack or the extension's offline
    // subset - a weaker read offline is expected, not a fault.
    const bandEl = document.getElementById('behavior-band');
    if (bandEl) {
      if (details.behaviorBand && details.behaviorBand !== 'none') {
        const src = details.behaviorSource === 'offline' ? 'offline check' : 'full analysis';
        bandEl.textContent = `${details.behaviorBand.toUpperCase()} · ${details.behaviorScore ?? '--'}/100 · ${src}`;
        bandEl.className = `behavior-band band-${details.behaviorBand}`;
        bandEl.style.display = 'inline-block';
      } else {
        bandEl.style.display = 'none';
      }
    }
    behaviorList.innerHTML = behavioral.map(item => `
      <div class="detail-item">
        <div class="detail-item-meta">${escapeHtml(item.severity || 'info')}</div>
        <div class="detail-item-title">${escapeHtml(item.title || 'Behavioral cue')}</div>
        <div class="detail-item-text">${escapeHtml(item.detail || '')}</div>
        ${item.evidence ? `<div class="detail-item-text">Evidence: ${escapeHtml(item.evidence)}</div>` : ''}
      </div>
    `).join('');
  } else {
    behaviorSection.style.display = 'none';
  }

  const conversation = details.conversation || null;
  if (conversation) {
    conversationSection.style.display = 'block';
    conversationStats.innerHTML = [
      { label: 'Segments', value: conversation.lineCount ?? 0 },
      { label: 'Links', value: conversation.linkCount ?? 0 },
      { label: 'Money', value: conversation.moneyMentions ?? 0 },
      { label: 'Codes', value: conversation.codeMentions ?? 0 },
    ].map(stat => `
      <div class="mini-stat">
        <div class="mini-stat-value">${escapeHtml(String(stat.value))}</div>
        <div class="mini-stat-label">${escapeHtml(stat.label)}</div>
      </div>
    `).join('');
    conversationList.innerHTML = (conversation.observations || []).map(item => `
      <div class="detail-item">
        <div class="detail-item-text">${escapeHtml(item)}</div>
      </div>
    `).join('');
  } else {
    conversationSection.style.display = 'none';
  }

  const mediaItems = [];
  (details.media?.images || []).forEach(image => {
    mediaItems.push(`
      <div class="detail-item">
        <div class="detail-item-meta">Photo</div>
        <div class="detail-item-title">${escapeHtml(image.title || 'Visible image')}</div>
        <div class="detail-item-text">${escapeHtml(image.detail || 'No caption or metadata found.')}</div>
      </div>
    `);
  });
  (details.media?.qrCodes || []).forEach(code => {
    mediaItems.push(`
      <div class="detail-item">
        <div class="detail-item-meta">QR ${escapeHtml(code.type || '')}</div>
        <div class="detail-item-title">${escapeHtml(truncateText(code.value || '', 100))}</div>
        <div class="detail-item-text">${escapeHtml(code.note || '')}</div>
        ${code.host ? `<div class="detail-item-text">Host: ${escapeHtml(code.host)}</div>` : ''}
        ${code.nearbyText ? `<div class="detail-item-text">Nearby text: ${escapeHtml(code.nearbyText)}</div>` : ''}
      </div>
    `);
  });

  if (mediaItems.length > 0) {
    mediaSection.style.display = 'block';
    mediaList.innerHTML = mediaItems.join('');
  } else {
    mediaSection.style.display = 'none';
  }
}

function renderAssessment(assessment) {
  if (!assessment) return;
  currentAssessment = assessment;

  renderTrustScore(assessment.trustScore);
  renderRiskBadge(assessment.riskLevel);
  renderPageInfo(assessment.title, assessment.url);
  renderScoreScope(assessment.url);
  renderSignals(assessment.signals, assessment);
  renderDeepAnalysis(assessment.analysisDetails);
  renderFactCheck(assessment.factCheck, assessment.isNewsArticle);
  renderRecommendations(assessment.recommendations);
  // F-B1/F-B2: render from the analyze block if present, else fetch independently.
  if (assessment.securities) {
    renderSecuritiesIdentity(assessment.securities);
  } else {
    loadSecuritiesForTab(assessment);
  }
  // Message-level authenticity, independent of sender identity.
  loadCommsForTab(assessment);

  // Show copy button
  document.getElementById('copy-evidence-btn').style.display = 'inline-block';
}

// --- F-B1/F-B2 Securities identity card ---

const SECURITIES_STATE_META = {
  valid:          { label: 'Registration verified',        cls: 'ok',   icon: '✓' },
  weak_match:     { label: 'Partial name match',           cls: 'warn', icon: '≈' },
  not_applicable: { label: 'No securities claim',          cls: 'mute', icon: '—' },
  unverified:     { label: 'Could not verify registration', cls: 'mute', icon: '?' },
  absent:         { label: 'Registration not disclosed',   cls: 'warn', icon: '!' },
  invalid:        { label: 'Registration does not resolve', cls: 'bad',  icon: '✕' },
  collision:      { label: 'Registration impersonation',   cls: 'bad',  icon: '⚠' },
  unavailable:    { label: 'Identity check unavailable',   cls: 'mute', icon: '—' },
};

function renderSecuritiesIdentity(sec) {
  const section = document.getElementById('securities-section');
  if (!section) return;
  if (!sec || !sec.state || sec.state === 'not_applicable') {
    section.style.display = 'none';
    return;
  }
  const meta = SECURITIES_STATE_META[sec.state] || SECURITIES_STATE_META.unavailable;
  let html = `<div class="sec-state sec-${meta.cls}"><span class="sec-icon">${meta.icon}</span> ${escapeHtml(meta.label)}</div>`;

  (sec.claims || []).forEach((c, i) => {
    const claimId = `sec-claim-${i}-${(c.number || '').replace(/[^A-Za-z0-9]/g, '')}`;
    html += `<div class="sec-claim" id="${claimId}"><strong>${escapeHtml(c.number)}</strong>` +
      (c.resolved_name ? ` &rarr; ${escapeHtml(c.resolved_name)}` : '') +
      (c.name_match_score != null ? ` <span class="muted-text">(${c.name_match_score}% name match)</span>` : '') +
      // Snapshot coverage is now 18 categories rather than 2, but a number
      // outside even that set — or one the user just wants double-checked
      // right now, not as of the last scrape — gets one click to a REAL,
      // rate-limited, live query against SEBI's own site. Never automatic:
      // this is a network call to a government server, so it only happens
      // on explicit request (same rule the hover card follows for redirect
      // resolution).
      (['unverified', 'weak_match', 'invalid'].includes(sec.state)
        ? ` <button type="button" class="sec-verify-live-btn" data-reg="${escapeHtml(c.number)}" data-claim="${claimId}">Verify live on SEBI ↗</button>`
        : '') +
      `<div class="sec-live-result" data-claim-result="${claimId}"></div>` +
      `</div>`;
  });

  (sec.upi || []).forEach((u) => {
    const ok = u.in_valid_namespace;
    html += `<div class="sec-upi ${ok ? 'sec-ok' : 'sec-warn'}">UPI ${escapeHtml(u.upi_id)} — ` +
      (ok ? 'in @valid namespace' : `outside @valid · <a href="${escapeHtml(u.sebi_check_url || '#')}" target="_blank" rel="noopener">verify on SEBI Check</a>`) +
      `</div>`;
  });

  if ((sec.typologies_matched || []).length) {
    html += '<div class="sec-typologies"><div class="detail-label">Matched SEBI typologies</div>';
    sec.typologies_matched.forEach((t) => {
      html += `<div class="sec-typology">${escapeHtml(t.id)} ` +
        (t.source ? `<a href="${escapeHtml(t.source)}" target="_blank" rel="noopener">source</a>` : '') + `</div>`;
    });
    html += '</div>';
  }

  // Reason codes - never a bare number (F-C2).
  if ((sec.reasons || []).length) {
    html += '<ul class="sec-reasons">';
    sec.reasons.forEach((r) => {
      const src = r.source_url ? ` <a href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener">[source]</a>` : '';
      html += `<li>${escapeHtml(r.text)}${src}</li>`;
    });
    html += '</ul>';
  }

  // Inherited design law: missing credentials are not proof of deception.
  if (sec.state === 'absent') {
    html += `<p class="sec-disclaimer">A missing registration number is a compliance gap to check — it is not, on its own, proof of a scam.</p>`;
  }
  if (sec.state === 'unverified') {
    html += `<p class="sec-disclaimer">This number is not in the bundled register subset, so it could not be checked either way. That is a limit of our offline data — not a finding against this entity. Confirm on the SEBI intermediary search.</p>`;
  }

  document.getElementById('securities-body').innerHTML = html;
  const asof = document.getElementById('securities-asof');
  asof.textContent = sec.register_as_of ? `Register data as of ${sec.register_as_of} · ${sec.source === 'offline_quickcheck' ? 'offline check' : 'backend'}` : '';
  section.style.display = 'block';

  // Wire the live-verify buttons just rendered. Delegated per-click (not
  // addEventListener in the loop above) so re-rendering this section never
  // stacks duplicate listeners on stale nodes.
  section.querySelectorAll('.sec-verify-live-btn').forEach((btn) => {
    btn.addEventListener('click', () => runLiveVerify(btn), { once: false });
  });
}

// --- Official communications authenticity ---
//
// Authenticates the MESSAGE, where the securities card above authenticates
// the SENDER. A fabricated "SEBI circular" passes every sender check in this
// product, because it never claims to come from a registered intermediary at
// all — it claims to come from the regulator.

const COMMS_STATE_META = {
  matched_exact:     { label: 'Official reference confirmed',   cls: 'ok',   icon: '✓' },
  matched_reference: { label: 'Reference exists, wording differs', cls: 'warn', icon: '≈' },
  not_in_index:      { label: 'No official record of this reference', cls: 'bad', icon: '✕' },
  index_unavailable: { label: 'Could not be checked',           cls: 'mute', icon: '?' },
  no_claim:          { label: 'No official communication claimed', cls: 'mute', icon: '—' },
};

function renderCommsVerdict(comms) {
  const section = document.getElementById('comms-section');
  if (!section) return;
  if (!comms || !comms.state || comms.state === 'no_claim') {
    section.style.display = 'none';
    return;
  }
  const meta = COMMS_STATE_META[comms.state] || COMMS_STATE_META.index_unavailable;
  let html = `<div class="sec-state sec-${meta.cls}"><span class="sec-icon">${meta.icon}</span> ${escapeHtml(meta.label)}</div>`;

  (comms.claims || []).forEach((c) => {
    html += `<div class="sec-claim"><strong>${escapeHtml(c.reference)}</strong>` +
      (c.title ? ` — ${escapeHtml(c.title)}` : '') +
      (c.published_at ? ` <span class="muted-text">(${escapeHtml(c.published_at)})</span>` : '') +
      (c.official_url ? ` · <a href="${escapeHtml(c.official_url)}" target="_blank" rel="noopener">official copy</a>` : '') +
      `</div>`;
  });

  if ((comms.reasons || []).length) {
    html += '<ul class="sec-reasons">';
    comms.reasons.forEach((r) => {
      const src = r.source_url ? ` <a href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener">[source]</a>` : '';
      html += `<li>${escapeHtml(r.text)}${src}</li>`;
    });
    html += '</ul>';
  }

  // Coverage is shown on the two states where it changes how the result
  // should be read. An index that starts in 2024 cannot speak to a 2019
  // circular, and saying so is the difference between a bounded answer and
  // an accusation.
  const cov = comms.coverage || {};
  if (cov.from_year && cov.to_year &&
      ['not_in_index', 'index_unavailable'].includes(comms.state)) {
    html += `<p class="sec-disclaimer">This index covers ${escapeHtml(String(cov.from_year))}–${escapeHtml(String(cov.to_year))}. References outside that window cannot be checked either way.</p>`;
  }
  if (comms.disclosure) {
    html += `<p class="sec-disclaimer">${escapeHtml(comms.disclosure)}</p>`;
  }

  document.getElementById('comms-body').innerHTML = html;
  const asof = document.getElementById('comms-asof');
  asof.textContent = comms.index_as_of ? `Official index as of ${comms.index_as_of}` : '';
  section.style.display = 'block';
}

async function loadCommsForTab(assessment) {
  try {
    let text = assessment.pageText || assessment.visibleText || '';
    const tab = await getActiveTab();
    if ((!text || text.length < 40) && tab?.id) {
      const snap = await sendMsg({ action: 'snapshotPage', tabId: tab.id });
      text = (snap && (snap.visibleText || snap.pageText)) || text || '';
    }
    const comms = await sendMsg({
      action: 'commsVerify',
      text: `${assessment.title || ''}\n${text}`,
    });
    renderCommsVerdict(comms);
  } catch (e) {
    renderCommsVerdict(null);
  }
}

async function runLiveVerify(btn) {
  const reg = btn.dataset.reg;
  const resultEl = document.querySelector(`[data-claim-result="${btn.dataset.claim}"]`);
  if (!reg || !resultEl) return;

  btn.disabled = true;
  btn.textContent = 'Checking SEBI live…';
  resultEl.innerHTML = '';

  try {
    const res = await sendMsg({ action: 'liveVerifyOfficial', reg_number: reg });
    if (!res || res.error && !res.checked) {
      resultEl.innerHTML = `<p class="sec-disclaimer">Live check unavailable: ${escapeHtml((res && res.error) || 'backend not reachable')}. The offline result above still stands — this only adds a real-time cross-check, it does not replace it.</p>`;
    } else if (res.matched) {
      resultEl.innerHTML = `<div class="sec-live-ok">✓ Confirmed live on SEBI's register` +
        (res.registered_name ? ` as <strong>${escapeHtml(res.registered_name)}</strong>` : '') +
        (res.category_tried ? ` (${escapeHtml(res.category_tried)})` : '') +
        (res.checked_at ? ` <span class="muted-text">checked ${escapeHtml(res.checked_at)}</span>` : '') +
        (res.source_url ? ` · <a href="${escapeHtml(res.source_url)}" target="_blank" rel="noopener">view on sebi.gov.in</a>` : '') +
        `</div>`;
    } else {
      resultEl.innerHTML = `<p class="sec-disclaimer">SEBI's own site returned no matching record just now` +
        (res.category_tried ? ` (checked: ${escapeHtml(res.category_tried)})` : '') +
        `. This is a live result, not a stored one — but a miss is still not proof of invalidity if the number belongs to a category we didn't probe. Confirm directly: ` +
        `<a href="https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognised=yes" target="_blank" rel="noopener">SEBI Recognised Intermediaries</a>.</p>`;
    }
  } catch (e) {
    resultEl.innerHTML = `<p class="sec-disclaimer">Live check failed: ${escapeHtml(String(e.message || e))}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Verify live on SEBI ↗';
  }
}

async function loadSecuritiesForTab(assessment) {
  try {
    let text = assessment.pageText || assessment.visibleText || '';
    const tab = await getActiveTab();
    if ((!text || text.length < 40) && tab?.id) {
      const snap = await sendMsg({ action: 'snapshotPage', tabId: tab.id });
      text = (snap && (snap.visibleText || snap.pageText)) || text || '';
    }
    const sec = await sendMsg({
      action: 'securitiesCheck',
      text: `${assessment.title || ''}\n${text}`,
      url: assessment.url || '',
    });
    renderSecuritiesIdentity(sec);
  } catch (e) {
    renderSecuritiesIdentity(null);
  }
}

function renderEmpty() {
  document.getElementById('trust-score').textContent = '--';
  document.getElementById('ring-fill').style.strokeDashoffset = RING_CIRCUMFERENCE;
  document.getElementById('ring-fill').style.stroke = '#64748b';
  renderRiskBadge('NOT SCANNED');
  renderPageInfo('Navigate to a page', '\u2014');
  document.getElementById('signals-section').style.display = 'none';
  const secSection = document.getElementById('securities-section');
  if (secSection) secSection.style.display = 'none';
  document.getElementById('summary-section').style.display = 'none';
  document.getElementById('behavior-section').style.display = 'none';
  document.getElementById('conversation-section').style.display = 'none';
  document.getElementById('media-section').style.display = 'none';
  document.getElementById('factcheck-section').style.display = 'none';
  document.getElementById('recommendations-section').style.display = 'none';
  document.getElementById('copy-evidence-btn').style.display = 'none';
  currentAssessment = null;
}

async function renderHistory() {
  const list = document.getElementById('history-list');
  const history = await sendMsg({ action: 'getHistory' });

  if (!history || history.length === 0) {
    list.innerHTML = '<p class="muted-text">No scan history yet.</p>';
    return;
  }

  list.innerHTML = history.slice(0, 10).map((h, i) => {
    const color = getColor(h.score);
    const borderColor = color + '44';
    return `
      <div class="history-item" data-index="${i}" title="${escapeHtml(h.url)}">
        <div class="history-score" style="border: 2px solid ${borderColor}; color: ${color};">
          ${Math.round(h.score)}
        </div>
        <div class="history-info">
          <div class="history-title">${escapeHtml(h.title || 'Unknown')}</div>
          <div class="history-url">${escapeHtml(h.url || '')}</div>
        </div>
        <span class="history-time">${timeAgo(h.timestamp)}</span>
      </div>
    `;
  }).join('');
}

// --- Connection Status ---

async function checkConnection() {
  const status = document.getElementById('connection-status');
  const text = status.querySelector('.status-text');

  const result = await sendMsg({ action: 'checkHealth' });

  if (result?.online) {
    status.className = 'connection-status online';
    text.textContent = 'Backend Online';
  } else {
    status.className = 'connection-status offline';
    text.textContent = 'Backend Offline';
  }
}

// --- Scan ---

async function scanPage() {
  const btn = document.getElementById('scan-btn');
  btn.textContent = 'Scanning...';
  btn.disabled = true;

  try {
    const result = await sendMsg({ action: 'scanActiveTab' });

    if (result?.error) {
      btn.textContent = result.error;
      setTimeout(() => {
        btn.textContent = 'Scan This Page';
        btn.disabled = false;
      }, 2000);
      return;
    }

    renderAssessment(result);
    await renderHistory();
  } catch (err) {
    btn.textContent = 'Error: ' + (err.message || 'Unknown');
  }

  btn.textContent = 'Scan This Page';
  btn.disabled = false;
}

async function ensureCurrentTabAssessment() {
  const activeTab = await getActiveTab();
  if (!activeTab?.id) {
    renderEmpty();
    return;
  }

  const lastScan = await sendMsg({ action: 'getLastScan', tabId: activeTab.id });
  if (lastScan && (!activeTab.url || lastScan.url === activeTab.url)) {
    renderAssessment(lastScan);
    return;
  }

  if (activeTab.url && /^https?:\/\//.test(activeTab.url)) {
    await scanPage();
    return;
  }

  renderEmpty();
}

// --- Copy Evidence ---

function copyEvidence() {
  if (!currentAssessment) return;

  const evidence = {
    phisherman_version: '6.0.0',
    timestamp: new Date(currentAssessment.timestamp).toISOString(),
    url: currentAssessment.url,
    title: currentAssessment.title,
    trustScore: currentAssessment.trustScore,
    riskLevel: currentAssessment.riskLevel,
    signals: currentAssessment.signals,
    recommendations: currentAssessment.recommendations,
    factCheck: currentAssessment.factCheck,
    analysisDetails: currentAssessment.analysisDetails || null,
  };

  navigator.clipboard.writeText(JSON.stringify(evidence, null, 2)).then(() => {
    const btn = document.getElementById('copy-evidence-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => { btn.textContent = 'Copy Evidence'; }, 1500);
  });
}

// --- Tab Change Listener ---

chrome.tabs.onActivated?.addListener(async (activeInfo) => {
  const lastScan = await sendMsg({ action: 'getLastScan', tabId: activeInfo.tabId });
  if (lastScan) {
    renderAssessment(lastScan);
  } else {
    await ensureCurrentTabAssessment();
  }
});

chrome.tabs.onUpdated?.addListener(async (tabId, changeInfo) => {
  if (changeInfo.status !== 'complete') return;
  const tab = await getActiveTab();
  if (tab && tab.id === tabId) {
    const lastScan = await sendMsg({ action: 'getLastScan', tabId });
    if (lastScan) {
      renderAssessment(lastScan);
    } else {
      await ensureCurrentTabAssessment();
    }
  }
});

// --- Stale-state clearing ---
//
// The panel used to have no message listener at all, so nothing could ever
// tell it that its contents had gone out of date. On a single-page messaging
// app that is a safety problem rather than a cosmetic one: switching
// conversation swaps the message list without any navigation event, and the
// panel carried on showing the previous chat's score, signals and captured
// text next to a completely different conversation.
//
// A stale reassuring verdict is worse than no verdict. It hands the user a
// reason to relax that was calculated about somebody else's messages.

const CLEARABLE_SECTIONS = [
  'signals-section', 'securities-section', 'comms-section', 'summary-section',
  'behavior-section', 'conversation-section', 'media-section',
  'factcheck-section', 'recommendations-section',
];

function clearAssessment(notice) {
  currentAssessment = null;
  CLEARABLE_SECTIONS.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  // Blank the captured-text blocks explicitly. Hiding the section leaves the
  // old text in the DOM, and it reappears the moment anything re-shows that
  // block for a different reason.
  ['selected-text', 'surrounding-text', 'analysis-summary'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = '';
  });
  const copyBtn = document.getElementById('copy-evidence-btn');
  if (copyBtn) copyBtn.style.display = 'none';

  const trust = document.getElementById('trust-section');
  if (trust && notice) {
    const badge = document.getElementById('risk-badge');
    if (badge) {
      badge.textContent = 'NOT SCANNED';
      badge.className = 'risk-badge risk-unknown';
    }
    const score = document.getElementById('trust-score');
    if (score) score.textContent = '–';
    const pageTitle = document.getElementById('page-title');
    if (pageTitle) pageTitle.textContent = notice;
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.action === 'panelClearAssessment') {
    const who = message.chatTitle ? ` — ${message.chatTitle}` : '';
    clearAssessment(`Conversation changed${who}. Scan to assess this chat.`);
  }
});

// --- Init ---

document.addEventListener('DOMContentLoaded', async () => {
  // Bind buttons
  document.getElementById('scan-btn').addEventListener('click', scanPage);
  document.getElementById('copy-evidence-btn').addEventListener('click', copyEvidence);
  document.getElementById('settings-link').addEventListener('click', (e) => {
    e.preventDefault();
    chrome.runtime.openOptionsPage();
  });

  // Check connection
  await checkConnection();

  // Load last scan for active tab, or auto-scan if missing
  try {
    await ensureCurrentTabAssessment();
  } catch {
    renderEmpty();
  }

  // Load history
  await renderHistory();
});
