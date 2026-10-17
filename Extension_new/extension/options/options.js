// Phisherman AI v6 - Options Page Logic

const DEFAULT_SETTINGS = {
  backendUrl: 'http://127.0.0.1:8000',
  verifierUrl: 'http://127.0.0.1:8000',
  analysisMode: 'local',
  quietBrowsing: true,
  autoScan: true,
  submitGuard: true,
  overlayPosition: 'bottom-right',
  overlayAutoHide: 10000,
  linkHoverTooltips: true,
  // Off by default: it makes a network request the user did not initiate.
  resolveRedirects: false
};

const fields = {
  verifierUrl: document.getElementById('verifierUrl'),
  analysisMode: document.getElementById('analysisMode'),
  quietBrowsing: document.getElementById('quietBrowsing'),
  backendUrl: document.getElementById('backendUrl'),
  autoScan: document.getElementById('autoScan'),
  submitGuard: document.getElementById('submitGuard'),
  linkHoverTooltips: document.getElementById('linkHoverTooltips'),
  resolveRedirects: document.getElementById('resolveRedirects'),
  overlayPosition: document.getElementById('overlayPosition'),
  overlayAutoHide: document.getElementById('overlayAutoHide')
};

function loadSettingsIntoUI(settings) {
  const s = { ...DEFAULT_SETTINGS, ...settings };
  for (const key of ['backendUrl', 'verifierUrl']) {
    if (/^http:\/\/(?:127\.0\.0\.1|localhost):879[89]\/?$/.test(s[key] || '')) s[key] = 'http://127.0.0.1:8000';
  }
  fields.analysisMode.value = s.analysisMode;
  fields.quietBrowsing.checked = s.quietBrowsing;
  fields.backendUrl.value = s.backendUrl;
  fields.verifierUrl.value = s.verifierUrl;
  fields.autoScan.checked = s.autoScan;
  fields.submitGuard.checked = s.submitGuard;
  fields.linkHoverTooltips.checked = s.linkHoverTooltips;
  fields.resolveRedirects.checked = s.resolveRedirects === true;
  fields.overlayPosition.value = s.overlayPosition;
  fields.overlayAutoHide.value = String(s.overlayAutoHide);
}

function readSettingsFromUI() {
  return {
    verifierUrl: fields.verifierUrl.value.trim() || DEFAULT_SETTINGS.verifierUrl,
    analysisMode: fields.analysisMode.value,
    quietBrowsing: fields.quietBrowsing.checked,
    backendUrl: fields.backendUrl.value.trim() || DEFAULT_SETTINGS.backendUrl,
    autoScan: fields.autoScan.checked,
    submitGuard: fields.submitGuard.checked,
    linkHoverTooltips: fields.linkHoverTooltips.checked,
    resolveRedirects: fields.resolveRedirects.checked,
    overlayPosition: fields.overlayPosition.value,
    overlayAutoHide: parseInt(fields.overlayAutoHide.value, 10)
  };
}

function showSaved() {
  const status = document.getElementById('saveStatus');
  status.classList.add('visible');
  setTimeout(() => status.classList.remove('visible'), 2000);
}

// Load
chrome.runtime.sendMessage({ action: 'getSettings' }, (settings) => {
  if (settings) loadSettingsIntoUI(settings);
});

// Save
document.getElementById('saveBtn').addEventListener('click', () => {
  const settings = readSettingsFromUI();
  chrome.runtime.sendMessage({ action: 'saveSettings', settings }, (response) => {
    if (response?.error) { alert(response.error); return; }
    showSaved();
  });
});

// Clear history
document.getElementById('clearHistory').addEventListener('click', () => {
  if (confirm('Clear all scan history?')) {
    chrome.runtime.sendMessage({ action: 'clearHistory' }, () => {
      const btn = document.getElementById('clearHistory');
      btn.textContent = 'Cleared!';
      setTimeout(() => { btn.textContent = 'Clear History'; }, 1500);
    });
  }
});

async function renderPersonalSites() {
  const entries = await chrome.runtime.sendMessage({ action: 'getPersonalSites' });
  const list = document.getElementById('personalSites');
  list.replaceChildren();
  for (const entry of entries || []) {
    const row = document.createElement('div');
    const label = document.createElement('span');
    label.textContent = entry.hostname + ' (expires ' + new Date(entry.expiresAt).toLocaleDateString() + ') ';
    const button = document.createElement('button');
    button.textContent = 'Remove';
    button.onclick = async () => {
      await chrome.runtime.sendMessage({ action: 'removePersonalSite', hostname: entry.hostname });
      renderPersonalSites();
    };
    row.append(label, button); list.append(row);
  }
  if (!list.childNodes.length) list.textContent = 'No remembered sites.';
  const reviewData = await chrome.storage.local.get('phisherman_review_requests');
  const count = (reviewData.phisherman_review_requests || []).length;
  document.getElementById('exportReviews').textContent = 'Export review requests (' + count + ')';
}
renderPersonalSites();
document.getElementById('exportReviews').onclick = async () => {
  const data = await chrome.storage.local.get('phisherman_review_requests');
  const blob = new Blob([JSON.stringify(data.phisherman_review_requests || [], null, 2)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'phisherman-feedback.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
};
document.getElementById('submitReviews').onclick = async event => {
  if (!confirm('Send saved website hostnames and warning reasons to your configured backend? No page body is included. Requests remain pending and do not change the shared whitelist.')) return;
  event.target.disabled = true;
  try {
    const result = await chrome.runtime.sendMessage({ action: 'submitReviewRequests' });
    document.getElementById('reviewStatus').textContent = result.error || result.message;
  } finally { event.target.disabled = false; }
};
