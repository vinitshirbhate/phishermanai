# Phisherman AI 6.3.0 — MVP usage and validation

The extension now starts with on-device checks. Load `extension/` through Chrome's **Load unpacked** action, or reload an existing installation and refresh open tabs.

Extension workflow: [SVG preview](workflow.svg) · [editable Excalidraw](workflow.excalidraw). The diagram maps the current local-first flow, optional network modes, financial verification, storage, and safeguards. Regenerate both artifacts with `node scripts/gen_extension_workflow.cjs` from `Extension_new`.

## Analysis modes

| Mode | Behavior |
|---|---|
| On-device checks (default) | Bundled rules, registration data, attachment checks, and URL-model evidence. No analysis network requests. |
| Local server | Immediate local result, then optional loopback backend enhancement. Browser cloud fallback is disabled. |
| Enhanced remote checks | Immediate local result, then configured backend and cloud fallback. Page/message text and URL can leave the device. |

In settings, choose the mode before enabling a server. Local-server mode requires `localhost`, `127.0.0.1`, or `::1`. Backend redirects are refused. Shortened-link expansion additionally requires its own opt-in and remote mode.

The Python backend defaults to deterministic inference. `SCAMGATE_MAX_TIER=1` enables local Ollama; `SCAMGATE_MAX_TIER=2` also permits configured cloud providers. A backend operator's configuration governs further processing.

## Personal website preferences

Eligible weak CAUTION warnings offer **Recognize this site?**. Confirmation creates an exact-host preference lasting 30 days. Preferences reduce weak interruptions without increasing scores or hiding strong evidence. The prompt is limited to once per seven days per host. Remove entries in settings.

Use **Incorrect warning?** to save feedback locally. Export requests in settings, or explicitly submit them to your configured backend. Submission sends hostname and warning reasons, not a page body. The backend stores deduplicated pending requests and never promotes them into the shared allowlist automatically.

## Shared website dataset

`extension/data/website_allowlist.json` is the shared source. It consolidates 911 inherited entries and uses exact-host matching (with the conventional `www` alias). Broad shared hosting and public suffix entries are excluded. Entries are not newly ownership-verified by this migration.

After reviewing an entry, record its review source/date in the JSON and regenerate the browser bundle:

```powershell
.\.venv\Scripts\python.exe scripts\sync_allowlist.py
```

## Local backend

The unified `main:app` server provides browser analysis and financial verification on port **8000**. Set both extension endpoint fields to `http://127.0.0.1:8000`. `/health` reports filing-corpus readiness and `/api/health` reports browser engines. Build the filing corpus with `python -m data.load_all` from the sibling `email_detection` directory, using the same virtual environment.

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Select **Local server** in extension settings. Backend review ingestion is `POST /api/reviews`; it accepts `hostname` and at most five warning reasons of at most 300 characters each. A 202 response means pending storage, not approval.

## Reproduce validation

From `Extension_new`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node tests\mvp_browser_harness.js
.\.venv\Scripts\python.exe scripts\check_blocked_claims.py
.\.venv\Scripts\python.exe scripts\validate_sandbox.py
.\.venv\Scripts\python.exe eval\run_eval.py
```

Optional training dependencies are in `ml/requirements.txt`. The shipped model was generated with:

```powershell
.\.venv\Scripts\python.exe ml\train.py --limit 20000 --n-boot 200 --cv-folds 3
```

The model card records held-out URL metrics. They are not integrated browser accuracy. The VM harness writes `eval/mvp_latency.json` with 30 warm synthetic scans; its mocked storage, snapshots, and network do not establish real browser latency.

## Verification record — 2 October 2026

- Full Python suite: **184 passed**.
- After the final chat lifecycle changes, the WhatsApp, module reachability, and Gmail regression subset: **37 passed**.
- Node VM browser harness: **passed**, including on-device network isolation, exact-host preferences, expiry, invalid settings rejection, per-form destination evidence, local-first results, and no stale hostname verdict reuse.
- Development sandbox validation: **passed**, with existing development signing material.
- Blocked-claims scan: **passed**.
- Additional tenant-blocklist regression confirms that a malicious shared-hosting tenant is named without accusing its parent domain.
- URL model regenerated from the bundled dataset; metrics and limitations are recorded in `ml/model_card.md`.

## Remaining validation

Test the installed extension on clean websites, financial login flows, an unrelated credential-form destination, a securities registration mismatch, and WhatsApp chat switching/edited messages. Verify keyboard controls, warning placement, and network behavior with Chrome DevTools. Hosted services and a real WhatsApp account were not contacted during implementation verification.
