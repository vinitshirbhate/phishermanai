const DEFAULT_ENDPOINT = "http://127.0.0.1:8000";
const input = document.getElementById("endpoint");
const status = document.getElementById("status");

chrome.storage.local.get(["endpoint"], (cfg) => {
  input.value = cfg.endpoint || DEFAULT_ENDPOINT;
});

document.getElementById("save").addEventListener("click", () => {
  let value = input.value.trim() || DEFAULT_ENDPOINT;
  value = value.replace(/\/+$/, "");

  // Reject anything that is not a well-formed http(s) origin, so a typo cannot
  // silently redirect message text somewhere unintended.
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("bad protocol");
  } catch {
    status.textContent = "That is not a valid URL.";
    status.className = "";
    return;
  }

  chrome.storage.local.set({ endpoint: value }, () => {
    status.textContent = "Saved.";
    status.className = "saved";
    setTimeout(() => (status.textContent = ""), 2200);
  });
});

document.getElementById("revoke").addEventListener("click", () => {
  chrome.storage.local.set({ consent: false }, () => {
    status.textContent = "Consent withdrawn. Checking is now off.";
    status.className = "saved";
  });
});
