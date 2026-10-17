# Phisherman AI — Browser Guard MVP

A Chrome extension that checks rendered websites, links, financial identity claims, and visible chat messages for scam indicators. Version **6.3.0** defaults to on-device analysis and provides optional server enhancement, with a shared dark toolbar popup and side panel.

## Start using it

1. Open `chrome://extensions`, enable Developer mode, and choose **Load unpacked**.
2. Select the `extension/` directory, then refresh open website tabs.
3. Browse normally. Clean pages stay quiet; click the toolbar icon for the dark popup, then **Open side panel** for the persistent workspace.
4. Use extension settings to choose on-device, local-server, or enhanced remote analysis.

No npm build is required. [MVP usage](docs/MVP.md) explains the modes, feedback workflow, and validation. [Repository explainer](explainer.md) covers architecture, baseline findings, and current implementation status.

## What is implemented

- Immediate local page assessments with optional asynchronous enhancement.
- Link identity and deceptive-address checks, registration lookups, APK filename checks, and scam-language rules.
- A bundled URL model used as supporting evidence, with a documented model card.
- One shared website dataset consolidating 911 inherited entries; exact-host matching avoids blanket shared-hosting trust.
- Selective personal site preferences with 30-day expiry, removal controls, and prompt cooldown.
- Incorrect-warning feedback saved locally, exportable or explicitly submitted to a pending backend queue.
- Modular WhatsApp observers with health reporting and chat-state invalidation.
- Quiet browsing, evidence details, analysis coverage, and keyboard-accessible chat badges.
- Shared popup/side-panel tools for pasted text, links, and selected page text, with local checks independent of the page score.
- Explicit financial-claim verification against the separate filing API, showing reasons, matched filings, comparisons, and recommended actions.

An absence of findings is not a guarantee. APK checks use filenames/context, credibility checks use heuristics, and optional C2PA inspection reports provenance rather than a general synthetic-media verdict.

## Privacy and analysis modes

**On-device checks** send no analysis network requests. **Local server** contacts the configured loopback backend and disables the browser cloud fallback. **Enhanced remote checks** permit page/message text and URL transmission to the configured backend and cloud fallback. Link destination expansion requires a separate opt-in and remote mode.

The backend defaults to deterministic inference. Its operator can enable local Ollama with `SCAMGATE_MAX_TIER=1` or configured cloud inference with `SCAMGATE_MAX_TIER=2`. Browser mode does not audit the behavior of a server.

Personal exceptions change interruption preferences, not evidence or scores. Submitted feedback stays pending and never automatically modifies the shared website dataset.

## Optional local backend

From this directory, with a virtual environment active:

```powershell
python -m pip install -r backend/requirements.txt
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

In extension settings choose **Local server** and set both URLs to `http://127.0.0.1:8000`. One server exposes browser analysis and financial verification. API documentation is available at `/docs`; corpus health is `/health` and browser engine health is `/api/health`.

See [models/README.md](models/README.md) for optional Ollama setup and [ml/model_card.md](ml/model_card.md) for URL-model measurements.

## Optional financial verifier

PDF checking is available in the popup and side panel under **Check a PDF**. Choose Local server mode, select a PDF, confirm uploading it, and click **Check PDF and links**. The unified server extracts text and embedded links; the extension checks those destinations without opening them. Chrome's built-in PDF viewer does not support the normal page scanner or hover overlay. Restart the updated unified backend to enable `/api/analyze/pdf`. Image-only PDFs need OCR, which this workflow does not include.

The filing engine lives in `../email_detection` and is included by the unified `backend/main.py` server on **8000**. Build its corpus by running `python -m data.load_all` from that directory, using the same virtual environment. Start only the unified server above. Choose **Local server** mode and set both extension URLs to `http://127.0.0.1:8000`.

Paste a claim or use selected text in the popup/panel. **Check on device** needs no server. For filing verification, confirm the per-input checkbox and click **Verify financial claim**. Phone/email redaction is applied; this is not comprehensive anonymization. Financial evidence availability stays separate from website trust scores. Results live in worker memory, not extension storage.

Load `Extension_new/extension`, and disable the separate `email_detection/extension` if its old white WhatsApp popup is still visible.

If `/health` succeeds but `POST /verify` returns 404, stop the old server and start the unified entry point:

```powershell
Set-Location F:\chetana-browser\phishermanai\Extension_new
python -m pip install -r backend/requirements.txt
Set-Location backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Set both URLs to `http://127.0.0.1:8000`, choose **Local server** mode, and reload the extension. Saved conventional local URLs using ports 8798/8799 migrate to 8000. The verifier checks endpoint compatibility before submitting claim text.

## Demos and verification

Serve local demos from this directory:

```powershell
python -m http.server 8801
```

Open `http://localhost:8801/demo/`. Run checks with:

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest tests -q
node tests/mvp_browser_harness.js
node tests/financial_verifier_harness.js
python scripts/check_blocked_claims.py
python scripts/validate_sandbox.py
```

The automated suite and Node VM harness exercise code paths. They do not replace live Chrome, WhatsApp, usability, latency, or representative website accuracy testing. See [docs/MVP.md](docs/MVP.md) for the verification scope and remaining work.
