const DEFAULT_ENDPOINT = "http://127.0.0.1:8000";

function setBadge(el, text, tone) {
  el.textContent = text;
  el.className = `badge badge-${tone}`;
}

function refresh() {
  chrome.storage.local.get(["endpoint", "consent"], (cfg) => {
    const endpoint = cfg.endpoint || DEFAULT_ENDPOINT;
    document.getElementById("endpoint").textContent = endpoint;

    setBadge(
      document.getElementById("consent"),
      cfg.consent ? "yes" : "not yet",
      cfg.consent ? "ok" : "wait"
    );

    chrome.runtime.sendMessage({ type: "PHAI_HEALTH", endpoint }, (response) => {
      const health = document.getElementById("health");
      const corpus = document.getElementById("corpus");
      if (chrome.runtime.lastError || !response?.ok) {
        setBadge(health, "not running", "bad");
        corpus.textContent = "—";
        return;
      }
      const data = response.data;
      setBadge(health, data.status === "ok" ? "running" : data.status, data.status === "ok" ? "ok" : "wait");
      corpus.textContent = `${Number(data.filings).toLocaleString()} filings`;
    });
  });
}

document.getElementById("options").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

document.getElementById("revoke").addEventListener("click", () => {
  chrome.storage.local.set({ consent: false }, refresh);
});

refresh();
