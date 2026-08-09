/**
 * Service worker: the only place that talks to the network.
 *
 * It forwards one message text to the user's configured verifier and returns
 * the verdict. It holds no state, keeps no history, and contacts no host other
 * than the configured endpoint.
 */

const DEFAULT_ENDPOINT = "http://127.0.0.1:8000";
const TIMEOUT_MS = 15000;

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["endpoint", "consent"], (cfg) => {
    if (!cfg.endpoint) {
      chrome.storage.local.set({ endpoint: DEFAULT_ENDPOINT });
    }
    // Consent is never defaulted to true. The first check always asks.
    if (cfg.consent === undefined) {
      chrome.storage.local.set({ consent: false });
    }
  });
});

async function verify({ text, forwarded, endpoint }) {
  const base = endpoint || DEFAULT_ENDPOINT;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const form = new FormData();
    form.append("text", text);
    form.append("channel", "EXTENSION");

    const response = await fetch(`${base}/verify`, {
      method: "POST",
      body: form,
      signal: controller.signal,
      // No cookies or credentials are sent: this is an anonymous local call.
      credentials: "omit",
      cache: "no-store",
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      return { ok: false, error: `Verifier returned HTTP ${response.status}. ${detail.slice(0, 200)}` };
    }

    const data = await response.json();
    if (forwarded && data?.reasons) {
      // WhatsApp's own forwarding label is context the verifier cannot see.
      data.reasons.unshift({
        code: "FORWARDED_MESSAGE",
        message:
          "WhatsApp marks this message as forwarded. Investment advice that reaches " +
          "you through a chain of forwards has no accountable source.",
        evidence: { whatsapp_forward_label: true },
        severity: 2,
      });
    }
    return { ok: true, data };
  } catch (error) {
    const message =
      error.name === "AbortError"
        ? `No response from ${base} within ${TIMEOUT_MS / 1000}s.`
        : `Could not reach ${base}: ${error.message}`;
    return { ok: false, error: message };
  } finally {
    clearTimeout(timer);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "PHAI_VERIFY") {
    verify(message).then(sendResponse);
    return true; // keep the channel open for the async response
  }
  if (message?.type === "PHAI_HEALTH") {
    const base = message.endpoint || DEFAULT_ENDPOINT;
    fetch(`${base}/health`, { cache: "no-store", credentials: "omit" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data) => sendResponse({ ok: true, data }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }
  return false;
});
