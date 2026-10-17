# Extension_new — Repository Explainer

> **Updated on 2 October 2026:** Sections 1–11 preserve the initial code review and proposed roadmap. Several findings have since been addressed. [Section 12](#12-implemented-mvp-update--2-october-2026) is the authoritative status of the implemented MVP changes; [docs/MVP.md](docs/MVP.md) describes how to use them.

`Extension_new` is a browser scam and phishing detection system focused on Indian financial scams. It includes a Chrome extension, a Python API backend, reference datasets, optional AI models, and evaluation tools.

It checks websites, links, visible chat messages, and attachment filenames, then displays a trust score, warnings, and supporting evidence.

**Main finding:** the implementation is broader than a simple phishing classifier, but several README claims do not match the current code—especially the claim that nothing leaves your device.

This explanation is based on a static code review on 2 October 2026. The extension was not loaded in Chrome, the test suite was not run, and hosted services were not contacted. Findings describe this checkout, not independently verified deployment behavior.

## 1. Project Overview

The project tries to catch situations such as:

- A fake broker website impersonating a legitimate company.
- An investment message promising guaranteed profits.
- Someone claiming a SEBI registration number belonging to another entity.
- A WhatsApp message asking for an OTP or threatening an account freeze.
- A chat attachment advertising an unofficial or modified trading APK.
- A link whose displayed identity differs from its actual destination.

It combines two approaches:

**Deterministic checks:** patterns, domain parsing, registry lookups, blocklists, and filename checks.

**Optional AI analysis:** a local language model through Ollama and cloud model providers.

The output includes a numeric trust score and explanations. A higher score means fewer detected concerns; it is not proof that a website is trustworthy.

The neighboring [`phishing_detection/main.py`](../phishing_detection/main.py) is a separate FastAPI service using Hugging Face inference. No direct reference to that service was found in `Extension_new`. This folder has its own backend.

## 2. Technology Stack

| Area | Technology | Purpose |
|---|---|---|
| Browser extension | Chrome Manifest V3 | Permissions, script loading, background execution |
| Browser logic | Plain JavaScript | Page extraction, checks, messaging, caching |
| Interface | HTML and CSS | Floating warnings, side panel, settings |
| Backend | Python, FastAPI, Uvicorn | Analysis and verification endpoints |
| Validation | Pydantic | API request and response schemas |
| Persistence | SQLite and Chrome local storage | Reference records, observations, history, cached verdicts |
| Optional local AI | Ollama, `phi4-mini` | Deeper text analysis |
| Optional cloud AI | Groq / DeepSeek integrations | Escalated analysis when configured |
| URL model training | scikit-learn, NumPy, pandas | Logistic regression model training |
| Tests | pytest, Node-based harnesses | False positives, feature parity, module behavior |
| Additional verification | Optional C2PA SDK, cryptography | Media provenance and signed contracts |

The extension needs no npm build step. Its JavaScript files are loaded directly by Chrome.

The basic backend dependency list contains only FastAPI, Uvicorn, and Pydantic. Training and some optional tools need additional packages.

## 3. Folder Structure & Architecture

```text
Extension_new/
├── extension/                 Chrome extension
│   ├── manifest.json          Permissions and browser entry points
│   ├── background.js          Analysis coordinator and caches
│   ├── content_script.js      Reads page/message content; displays warnings
│   ├── preflight/             Link parsing and destination checks
│   ├── whatsapp/              Modular WhatsApp extraction and analysis
│   ├── shared/                Shared normalization, overlays, APK checks
│   ├── sidepanel/             Detailed results interface
│   ├── options/               Settings interface
│   ├── data/                  Bundled securities reference snapshot
│   └── contracts/             Policies, registries, signatures
├── backend/
│   ├── main.py                Uvicorn compatibility entry point
│   ├── api.py                 FastAPI routes and application setup
│   ├── store.py               SQLite storage
│   ├── engines/               Detection and verification modules
│   ├── data/                  Registries, patterns, threat feeds
│   └── scripts/               Feed refresh tools
├── ml/                        URL features, training, model documentation
├── models/                    Ollama model definitions and setup scripts
├── datasets/                  Training dataset cache
├── eval/                      Evaluation scripts and fixtures
├── tests/                     Automated tests
├── demo/                      Example pages
├── docs/                      Architecture and control documentation
├── scripts/                   Validation and diagram tools
├── schemas/                   Structured artifact schemas
├── state/                     Development signing state
└── main.py                    Empty file
```

This is a browser client plus backend architecture, with detection logic divided into modules. `background.js` is a large central coordinator, while individual checks live in smaller files.

### How a page scan works

1. **Chrome loads the extension.** [`manifest.json`](extension/manifest.json) registers a background service worker and content scripts for HTTP and HTTPS pages.
2. **The content script builds a snapshot.** [`content_script.js`](extension/content_script.js) collects the page URL and title, up to approximately 15,000 characters of page text, password/email/payment-field indicators, form destination hosts, visible link hosts, and messaging context and attachment filenames where available. On supported messaging surfaces, it tries to isolate messages instead of analyzing the entire interface. If it cannot isolate an open webmail message, it suppresses the verdict to avoid judging that email using unrelated inbox content.
3. **The background worker chooses an analysis source.** The actual page-analysis chain is shown below. The configured backend can itself use Ollama; the browser does not directly invoke Ollama in this chain.
4. **The result is normalized and supplemented.** Backend trust scores and cloud risk scores are converted to a common format. Attachment findings can lower the score.
5. **Chrome displays the assessment.** The extension updates its toolbar badge, shows a floating warning, and makes detailed evidence available in the side panel. It also saves scan history.

```text
Cached domain result
    → Configured backend
    → Cloud fallback API
    → Offline rules
```

The routing logic is in [`background.js`](extension/background.js).

### What the individual checks do

| Feature | Actual behavior |
|---|---|
| Link inspection | Parses the real host, checks deceptive URL structures, Unicode lookalikes, IP addresses, shorteners, and identity signals |
| Securities identity | Resolves claimed registration numbers against bundled records and checks name or contact associations |
| UPI checks | Examines handles against bundled namespace and fraud-reference data |
| Scam detection | Matches scam patterns and combines them with optional AI results |
| WhatsApp monitoring | Watches rendered message changes and flags suspicious incoming messages |
| APK checks | Uses attachment filenames and delivery context |
| “Fact checking” | Scores source credibility and suspicious language using deterministic heuristics |
| Media provenance | Can inspect C2PA credentials when the optional SDK is installed |
| Campaign tracking | Stores observations and entities to associate related activity |

A registration lookup establishes a relationship to a reference record. It does not establish that every statement or payment request made by that sender is legitimate.

### Backend analysis

[`api.py`](backend/api.py) exposes endpoints including:

```text
GET  /health
POST /api/analyze/page
POST /api/analyze/text
POST /api/analyze/url
POST /api/fact-check
POST /api/scamgate/scan
POST /api/securities/identity
POST /api/upi/verify
POST /api/link/inspect
POST /api/provenance/inspect
POST /api/comms/verify
GET  /api/history
GET  /api/stats
```

[`trust_engine.py`](backend/engines/trust_engine.py) combines scam detection, domain intelligence, credibility heuristics, manipulation detection, and form-related analysis.

Its sub-engine calls catch failures and continue with available results. This keeps the API working, but a returned assessment may have less evidence when an engine fails.

[`scamgate.py`](backend/engines/scamgate.py) implements three tiers:

- **L0:** local patterns and reference data.
- **L1:** optional local Ollama model.
- **L2:** optional cloud analysis using configured provider credentials.

### Trust score bands

The browser currently uses these thresholds:

| Score | Internal label |
|---|---|
| 80–100 | `SAFE` |
| 50–79 | `CAUTION` |
| 25–49 | `WARNING` |
| 0–24 | `DANGER` |

These are application thresholds, not calibrated probabilities.

If submit protection is enabled, a page assessed as `DANGER` triggers a confirmation before an ordinary form submission. The user can still proceed.

## 4. Important Findings in the Current Code

### A. Remote transmission is enabled by the default configuration

Both the background worker and settings page default to:

```text
https://phishermanai-1.onrender.com
```

The backend request sends page URL, title, text, or message text. If that backend fails, another request can go to:

```text
https://chetana.activemirror.ai/api/scan/full
```

That fallback sends up to 3,000 characters assembled from text, title, and URL. See `analyzeWithBackend` and `analyzeWithCloud` in [`background.js`](extension/background.js).

Therefore, the README’s “nothing leaves your device” statement is inaccurate for the default configuration. Setting a localhost backend also does not disable the separate cloud fallback.

### B. The URL machine-learning artifact is missing

The worker tries to load `extension/models/lr_v1.json`. That file is absent in this checkout. The optional URL ML scorer therefore cannot contribute until the artifact is generated or supplied.

The [model card](ml/model_card.md) describes a domain-feature logistic regression model, but those recorded metrics do not demonstrate the behavior of the currently installed extension.

### C. The modular WhatsApp adapter appears unwired

The manifest loads [`whatsapp/adapter_mv3.js`](extension/whatsapp/adapter_mv3.js), which exports a `start(deps)` function. No production call starting that adapter was found.

Meanwhile, `content_script.js` explicitly starts its own WhatsApp observer.

WhatsApp scanning exists, but the newer adapter’s health checks, retention limits, and lifecycle controls should not be assumed active merely because the file is loaded.

### D. “Fact checking” is a credibility heuristic

The fact-checking engine examines source ratings and language patterns. It is not a general system that researches and independently verifies every factual claim.

Likewise, APK inspection uses filenames and context—it does not analyze an APK’s executable contents.

### E. Cached verdicts can be reused across pages on the same host

The persistent cache is keyed by hostname and lasts 24 hours. Messaging surfaces are excluded, which helps avoid mixing unrelated chats.

For ordinary websites, however, a verdict from one page can be reused for a different page on the same hostname.

### F. Some browser signals do not reach backend analysis as intended

The extension sends form and link indicators inside a `signals` object, but `PageAnalysisRequest` does not declare that field. It declares `form_fields` instead.

Under the model’s default handling, those extra indicators are ignored. The backend still receives URL, title, and text, but this part of the browser-to-backend contract is inconsistent.

### G. Documentation and implementation have drifted

Examples include:

- README says the verdict is not a score; the implementation uses numeric trust scores.
- Backend documentation says localhost is detected automatically; the code checks the configured backend URL.
- Root `main.py` is empty.
- Policy text claims default local analysis despite the hosted backend default.
- Public-suffix handling uses a curated subset, rather than the full public suffix list.

The code is the more reliable guide to current behavior.

## 5. Onboarding Guide

### Load the browser extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `F:\chetana-browser\phishermanai\Extension_new\extension`.
5. Visit a normal website and open the extension’s side panel.

### Run the optional local backend

From PowerShell:

```powershell
cd F:\chetana-browser\phishermanai\Extension_new

py -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -r backend\requirements.txt

cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8799
```

An existing `.venv` is present in this checkout; creating one is only needed for a fresh setup.

Then change the extension’s **Backend URL** setting to `http://127.0.0.1:8799`.

Useful local URLs:

```text
http://127.0.0.1:8799/health
http://127.0.0.1:8799/docs
```

Remember that the separate browser cloud fallback remains in the code.

### Try the demo pages

From the `Extension_new` root:

```powershell
python -m http.server 8801
```

Open `http://localhost:8801/demo/`.

The demos cover phishing, securities scams, government claims, and fake payment proof.

### Optional local AI

With Ollama installed, run these commands from the project root:

```powershell
ollama pull phi4-mini
ollama create phisherman-guard -f models/phisherman-guard.Modelfile
```

The backend expects `phisherman-guard` by default. Building only the fast variant requires changing `SCAMGATE_MODEL`. See [`models/README.md`](models/README.md).

### Run the existing tests

From the project root, with backend dependencies installed:

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pytest tests -q
```

Some tests use Node harnesses, so Node may also be required. Optional tooling may need dependencies beyond the basic backend requirements.

### Best files to read first

1. [`manifest.json`](extension/manifest.json) — what Chrome loads and permits.
2. [`content_script.js`](extension/content_script.js) — what the extension reads and displays.
3. [`background.js`](extension/background.js) — request routing, fallbacks, scoring, and caches.
4. [`api.py`](backend/api.py) — backend contract.
5. [`trust_engine.py`](backend/engines/trust_engine.py) — combined analysis.
6. [`scamgate.py`](backend/engines/scamgate.py) — optional AI escalation.

## 6. Current Implementation Reality as a Hackathon MVP

The current checkout is a substantial prototype with useful detection logic and a browser interface. It is suitable for a focused hackathon demonstration after the integration gaps above are addressed. A seamless installation, reliable accuracy, and fast responses still need to be demonstrated through browser testing and measured evaluation.

The following assessment distinguishes code that exists from capabilities that are operationally verified. **“Implemented” means present in the source; it does not mean validated in a live browser or deployed service.**

| Capability | Current reality | MVP improvement |
|---|---|---|
| Automatic page checks | Implemented with navigation triggers and snapshots | Verify SPA navigation, prevent repeated scans, and show an immediate local result |
| Page warnings and side panel | Implemented | Make the first message short, explain the main concern, and offer one clear next action |
| Website allowlist | A substantial hardcoded `TRUSTED_HOSTS` list plus separate backend JSON data already exist | Audit coverage and unify the sources rather than simply adding many domains |
| User whitelist requests | No dedicated personal allowlist or review-request workflow was found in the inspected settings and routing | Add selective feedback and reversible personal exceptions |
| Offline detection | Implemented fallback rules, registration snapshot, and link checks | Make offline checks the immediate path and disclose their evidence limits |
| Optional URL ML | Scorer exists; expected model artifact is missing | Supply a versioned artifact and verify feature parity before enabling it |
| WhatsApp detection | Existing content-script observer runs; modular adapter appears unstarted | Use one integrated observer and test chat switching, edits, deletions, and unreadable states |
| Local and remote analysis | Hosted backend is the default; a separate cloud fallback exists | Provide explicit analysis modes and make data transmission match the selected mode |
| Accuracy | Tests and historical model documentation exist | Measure the current end-to-end browser path on a representative held-out set |
| Response speed | Cache and hover checks exist, but page analysis can wait through sequential network calls | Return local evidence first, update asynchronously, and measure actual latency |
| Media and file checks | Filename checks and optional credential inspection exist | Describe their scope clearly; avoid presenting them as malware or deepfake detection |

### What can honestly be demonstrated

A focused demo can show a deceptive link, an investment pitch with a registration mismatch, an APK offer in chat, and an ordinary legitimate page. Each should show the actual reason, the source of the evidence, and the user action available.

Do not claim a detection percentage, zero false positives, or a response-time guarantee based only on the README or model card. Run the shipped analysis path, retain the results, and distinguish rule-based, model-based, and integrated system metrics.

## 7. Proposed Feature: Selective User Whitelist Requests

The user should be able to correct an unhelpful warning without repeatedly dismissing it. This is a **proposed feature**, not currently implemented.

### Ask only on selected cases

Offer a small, non-blocking question when a site has a weak or uncertain warning, the user has visited it repeatedly, or the user opens “This warning seems incorrect.” Do not ask on every page or on every visit. Keep a dismissal cooldown and a per-site prompt limit.

Suggested copy:

> Do you recognize this website and want fewer low-confidence warnings for this exact site?

Actions:

- **Remember this site** — create a personal exception on this device.
- **Request review** — submit a false-positive report after showing what will be sent.
- **Keep checking** — leave the assessment unchanged and stop repeating the question for a defined period.

Explain the effect next to the choice: “This changes your warning preference. It does not verify the website.” Avoid asking users to certify that a site is objectively safe.

### Separate personal preferences from shared reputation

| Mechanism | Scope | Effect |
|---|---|---|
| Personal exception | This user and browser profile | Reduces repeated low-confidence interruptions |
| Review request | Pending submission | Records a suspected false positive without changing the verdict for everyone |
| Curated shared allowlist | All installations receiving that dataset | Adds a dated identity or reputation signal after review |

For the MVP, implement personal exceptions first. Store the normalized exact hostname, creation time, expiry, and reason in `chrome.storage.local`. Provide a visible list in settings with remove and reset actions. Choose a documented initial expiry, such as 30 days, and ask again only when it expires or relevant evidence changes.

Do not silently trust every subdomain. Trusting `example.com` should not automatically trust `uploads.example.com` unless the scope is explicitly reviewed. Never allow exceptions for broad shared hosting suffixes such as `github.io` or `vercel.app`; a specific tenant hostname needs its own entry.

A personal exception must not suppress strong evidence such as a known malicious URL hit, a resolved registration mismatch, or a credential form submitting to an unrelated destination. Preserve those findings and show “You remembered this site, but new evidence needs attention.”

User votes alone must not promote a site into the shared allowlist. A future review service can accept domain, reason code, optional explanation, and evidence timestamp, with validation, duplicate handling, and review status. Sending page or message contents should be a separate explicit choice.

## 8. Improving Website Detection Accuracy

Adding more rules or domains does not automatically improve accuracy. The immediate objective is fewer incorrect interruptions while retaining detection of meaningful threats.

### Correct the integration before adding model complexity

1. Align the browser payload with the backend schema so form and link evidence is actually consumed.
2. Supply or explicitly disable the missing URL model artifact and display the capabilities available.
3. Start the modular WhatsApp adapter correctly or consolidate its controls into the observer that actually runs.
4. Invalidate page-specific verdicts on URL, relevant content, and evidence-version changes. Keep domain reputation caching separate from page-content verdict caching.
5. Preserve an explicit **insufficient evidence** state when analysis cannot complete. A failed check should not produce a reassuring result.

### Improve the evidence used for decisions

- Compare the claimed brand with the actual host and credential-form destination. A suspicious suffix by itself should carry limited weight.
- Separate verified identity evidence, known malicious indicators, page behavior, and language heuristics. Show which kind supports each finding.
- Expand public-suffix coverage and test shared hosting, international domains, Unicode hosts, legitimate deep links, and redirect behavior.
- Use dated reference data with freshness indicators. “Not found in this snapshot” differs from “fraudulent.”
- Treat HTTPS as transport protection, not proof of the operator’s legitimacy.
- Evaluate local-language and mixed-language financial messages if these are in the demo scope.
- Keep deterministic evidence visible even when an LLM produces a different interpretation; do not let fluent model text override a confirmed identity mismatch.

### Measure the actual product

Build a held-out evaluation set containing legitimate banks, brokers, government services, universities, shopping sites, small businesses, login pages, and shared hosting tenants, alongside phishing and scam examples. Include matched cases such as an official registration page versus an impersonating page using the same brand words.

Separate training and tuning examples from final evaluation. Group related domains or campaigns together to avoid leakage. Report precision, recall, false-positive rate, confusion counts, sample sizes, and unavailable-analysis cases. Break results down by website category and analysis mode; one combined score can hide failures on real users’ common pages.

The historical URL model metrics in `ml/model_card.md` are not an end-to-end extension accuracy claim. Establish a baseline, change one significant component at a time, and retain a regression set for every real false-positive report.

## 9. Broader Website Allowlist Coverage

The extension already has a broad hardcoded list in `background.js`, while the backend reads `backend/data/domain_whitelist.json`. The improvement should be **reviewed coverage and consistent behavior**, not an unverified list of popular names.

Candidate categories include financial institutions and brokers, government services, education, healthcare, shopping, travel, workplace tools, and commonly used small-business services. Add only exact domains whose ownership or official association has been checked. These are coverage categories, not a verified recommendation to allowlist any particular site.

Use one versioned source to generate the extension and backend datasets. Each entry should record the hostname, entity, category, verification source, review date, expiry or next-review date, and allowed subdomain scope.

The existing backend whitelist matcher accepts listed domains and their subdomains. Review that behavior before extending the dataset, especially for sites hosting user-generated content or independent tenants.

Allowlist membership should contribute identity context and reduce weak false positives. It should not bypass inspection of a compromised page, a malicious tenant, an unrelated form destination, or a suspicious payment request. Unknown sites should remain assessable without being treated as malicious simply because they are absent from the list.

## 10. Seamless User Experience and Fast Responses

### Make ordinary browsing quiet

- Keep clean or low-evidence results in the toolbar badge; reserve prominent overlays for actionable concerns.
- Explain the main reason in one sentence, such as “This form sends details to a different website.” Put technical evidence behind “Details.”
- Offer clear next actions: return, inspect evidence, continue, or report an incorrect warning.
- Avoid repeated prompts on the same unchanged page and duplicate chat warnings.
- Show “Checking,” “Limited checks,” or “Could not check” when appropriate. Keep offline limitations visible without requiring the user to interpret backend status.
- Put simple analysis-mode choices in onboarding: local checks, local server, or enhanced remote checks. Make the selected mode control all fallbacks.
- Support keyboard navigation, readable contrast, and accessible warning announcements. Test overlay behavior on narrow screens and against page layout changes.

A normal user should install the extension and browse. Configuring API hosts and models belongs in advanced settings or developer setup.

### Return local evidence before waiting for the network

The current worker has health-check, backend, and cloud timeout limits of 5, 15, and 12 seconds. Depending on availability state, the sequential fallback path can delay the first page verdict by tens of seconds. These are configured timeout ceilings, not measured typical latency.

Proposed flow:

```text
Page or message snapshot
    → Immediate local checks
    → Display preliminary evidence
    → Optional remote enhancement in the background
    → Update only if the result still belongs to this page or message
```

Use cached backend health instead of probing on every scan. Deduplicate identical in-flight requests, debounce relevant DOM changes, and cancel obsolete work when the user navigates or changes chats. Apply a total deadline to remote enhancement and keep the local result usable if that deadline expires.

Keep hostname reputation caches separate from content assessments. Include relevant URL/context, content fingerprint, settings, and model/reference versions when reusing a page verdict. Never apply a delayed response to a different conversation or tab state.

Suggested **MVP performance targets to validate**, not existing guarantees:

| Interaction | Initial target |
|---|---|
| Local hover assessment after hover activation | p95 under 100 ms |
| Initial page result after a usable snapshot is available | p95 under 500 ms |
| Feedback after clicking a scan button | Visible progress within 100 ms |
| Optional remote enhancement | Total deadline of 3–5 seconds, then retain local evidence |
| Chat processing | Measure the existing adapter’s 8 ms/message and 50 ms/batch budgets after integration |

Measure snapshot extraction separately from scoring, network time, and rendering. Report p50 and p95 on stated hardware, with cold and warm caches, offline operation, and slow-network cases.

## 11. Prioritized Hackathon MVP Roadmap

| Priority | Work | Reviewable completion criterion |
|---|---|---|
| P0 | Correct claims and analysis modes | Documentation and UI describe actual data flows; local mode performs no remote analysis requests |
| P0 | Immediate local results | Offline and slow-backend demos remain responsive with visible evidence |
| P0 | Fix schema, cache, and WhatsApp integration | Relevant form signals reach analysis; pages and chats do not reuse unrelated verdicts; one intended observer runs |
| P0 | Establish accuracy baseline | Reproducible held-out results include false positives and unavailable checks |
| P1 | Personal whitelist preferences | Selective prompts, exact-host entries, expiry, removal, and strong-evidence override work |
| P1 | Curated allowlist consolidation | Browser and backend consume matching versioned entries with review metadata |
| P1 | Simplify warnings and settings | Ordinary browsing stays quiet; warnings explain one concern and offer a clear action |
| P1 | Validate optional ML | Artifact availability and feature parity are checked; results are compared with the rules-only baseline |
| P2 | Shared review workflow | Submitted feedback has consent, pending status, and a defined review process |
| P2 | Broader capabilities | Add language coverage, provenance tooling, and campaign views only with tests and clear limitations |

For a hackathon, prioritize a complete user journey: install, receive a fast understandable assessment, inspect evidence, correct an unhelpful warning, and continue browsing. Demonstrate that journey on both scam examples and legitimate sites before increasing the feature count.

All features and targets in Sections 7–11 are proposals. This documentation update does not implement them or establish new accuracy or latency measurements.

## 12. Implemented MVP Update — 2 October 2026

Implementation has begun and now covers the principal user journey. The descriptions below supersede the baseline findings where they differ.

| Improvement | Implemented behavior | Remaining limits |
|---|---|---|
| Selective personal whitelist | Eligible weak CAUTION findings offer an exact-site preference; 30-day expiry, remove controls, and seven-day prompt cooldown | Strong findings, messaging assessments, and unknown-severity warnings cannot be quieted |
| User review requests | Save locally, export JSON, or explicitly submit hostname and warning reasons through settings to `POST /api/reviews` | Submissions are pending; human moderation and automatic shared-list publication are not implemented |
| Broader consistent website coverage | One dataset consolidates 911 existing browser/backend entries; generated browser bundle and backend reader use that source | Existing entries are marked inherited, not newly verified; ownership review is still needed |
| Accuracy improvements | Per-form sensitive destination evidence, multi-label Indian domain parsing, no hostname-only page-verdict reuse, and model availability | External credential destinations trigger a review warning, not a fraud assertion; no representative live-web accuracy percentage established |
| Seamless browsing | Quiet browsing default, concise clean-state labels, source/coverage display, accessible chat badge activation, and simple mode settings | Visual layout and interactions still need live Chrome testing |
| Fast response | Local assessment first; optional asynchronous enhancement, bounded network requests, cached health, duplicate enhancement sharing, and stale-result checks | No live-browser p95 guarantee; VM timings are not browser performance |
| Optional ML | `extension/models/lr_v1.json` generated and available; model remains supporting URL evidence | Brier calibration target remains unmet; not evaluated specifically on Indian securities phishing |
| WhatsApp integration | Manifest bootstrap starts the modular adapter; legacy observer initialization removed; source-tab scans and chat-state invalidation wired | WhatsApp DOM changes can still reduce coverage; live account testing needed |
| Browser/backend contract | Password, email, and card indicators are accepted by the page request model and translated into form fields | More detailed form-behavior modeling can be added after representative evaluation |
| Privacy modes | Default on-device mode disables analysis network calls. Local server requires loopback. Remote mode explicitly permits backend/cloud analysis | Backend operators control optional inference providers; browser mode cannot audit a remote service |
| Development policy | Permission metadata reconciled without adding host access; development signatures regenerated and validator passes | Development signing is not production key management |

### Measured verification and scope

- The existing 181-test suite passed after the first implementation round. Additional API tests cover signal consumption and pending review deduplication. See the final verification record in [docs/MVP.md](docs/MVP.md).
- A Node VM harness exercises personal-exception scope/expiry, on-device privacy, same-site and cross-site credential forms, staged enhancement, and score preservation. It uses mocked browser APIs, not an installed Chrome extension.
- Training used a 20,000-row stratified sample from the bundled PhiUSIIL corpus with a domain-grouped split: 13,898 training rows and 6,102 test rows, with no overlapping registrable domains.
- Model MCC: **0.6370**; PR-AUC: **0.8907**; recall at a threshold targeting FPR <=1%: **0.5705**; Brier score: **0.1420**. The default-threshold confusion counts in the model card correspond to a different operating point from that FPR-targeted recall.
- The existing authentication/typology fixtures regenerated `eval/REPORT.md`; they are bounded fixture results, not a general website accuracy claim.
- `scripts/check_blocked_claims.py` and `scripts/validate_sandbox.py` passed. Signatures use the existing development signer.

### How the improved user journey works

1. Install or reload extension 6.2.0. Existing installations without a stored analysis mode migrate to on-device checks through the default settings.
2. Browse normally. The toolbar and side panel retain assessments while clean pages stay quiet.
3. A meaningful warning explains the main evidence. Weak eligible cases may offer “Recognize this site?” at most once per seven days per hostname.
4. Remembering a site reduces only eligible weak interruptions for 30 days. The score and evidence remain intact; stronger findings still appear.
5. “Incorrect warning?” saves feedback locally. Settings provide export and explicit submission. Submission requires a configured local server or remote mode and leaves the shared allowlist unchanged.
6. Optional server enhancement arrives after the local result. A newer scan, changed page content, changed URL, settings change, or chat switch invalidates an obsolete result.

### What is still future work

The remaining work includes live-browser usability and latency testing, independently reviewed ownership and freshness for allowlist entries, a representative end-to-end website evaluation corpus, reviewer administration, language-specific evaluation, and production distribution. These are not claimed complete by the current MVP.

## 13. Unified dark popup and side panel — implementation 6.3.0

### PDF checking

The popup and side panel now provide **Check a PDF**. Chrome's built-in PDF viewer and local `file://` pages cannot be scanned using the normal content-script flow; choose the document explicitly instead. Enable Local server mode, select a PDF, confirm uploading the full document without redaction, and run the check. The unified backend on port 8000 exposes `POST /api/analyze/pdf`, extracts readable text and embedded HTTP/HTTPS URI annotations (including links whose visible label is not a URL), and returns page-numbered destinations. Plain text URLs are also extracted. The UI runs local text rules and the existing preflight checks for each link, without automatically visiting link destinations. Documents are not persisted by this extraction endpoint.

Limits: 12 MB, 100 pages, 100,000 extracted characters and 200 unique links. Local text checks cover the first 15,000 characters. Password-protected PDFs are rejected. OCR, PDF JavaScript, attachments, internal navigation links, and direct hover cards inside Chrome's PDF viewer are outside this implementation. Image-only documents are identified as having no readable text; they are not reported as clean.

### Expanded website sources and link accuracy

Developer-site expansion: the dataset now includes **969 exact hosts**, with GitHub explicitly classified as a recognized developer service. `scripts/add_developer_sites.py` adds 16 previously absent hosts, including GitHub documentation/support/API, Python documentation, MDN, Microsoft Learn, Chrome developer documentation, web.dev, Docker documentation/Hub, GitLab documentation, Codeberg, and Ask Ubuntu. These curated host records are identity context, not a guarantee for community content. GitHub repository pages discussing remote-access tools do not trigger that rule unless they also request installation/download/access. Explicit OTP-sharing and remote-access demands remain flagged. Reload the extension and refresh existing tabs after updating; old injected content scripts and displayed warnings remain until refreshed.

`scripts/refresh_website_directory.py` fetches official directories and records each imported host's source, category, and review date. The first refresh added 45 hosts and reviewed 47 entries from India.gov.in and USA.gov, bringing the dataset to 953 after removing non-public IP entries. IGOD failed TLS certificate validation and was skipped. Refresh results are recorded in `eval/website_directory_refresh.json`; run `scripts/sync_allowlist.py` afterward to regenerate the browser bundle. Directory membership establishes identity context, not that every page or upload is safe. Inherited entries retain their pending review status. Exact-host matching remains in place; no blanket trust for shared hosting or all subdomains.

Hover checks now receive the visible link text, enabling the existing parser to compare a displayed URL/domain with the actual destination. Cache keys include that text so differently labelled links to the same URL are assessed separately. URL obfuscation, user-info tricks, shorteners, identity mismatches, and opted-in redirect checks remain available. Generic references to deepfakes, one-time passwords, or timing language no longer trigger the three overly broad local rules responsible for repository false positives. Explicit OTP-sharing demands and video-KYC pressure remain detectable. These are targeted regression improvements, not a measured guarantee of overall detection accuracy.

### Personal whitelist prompt and link hover usability

Eligible new sites with weak CAUTION findings now show a bottom-right prompt for 10 seconds. It asks one question, **Do you trust this website?**, with **Add to my whitelist** and **Not now**. Adding requires no second browser confirmation. The exact-host personal preference lasts 30 days, reduces only eligible weak warnings, and is removable in Settings. Strong findings remain visible, and adding a preference does not certify safety or change the shared website list. Existing seven-day per-host prompt cooldown avoids repeated interruptions. Navigation changes are checked before saving.

Link hover cards now show immediate checking feedback, the full destination, whether it leaves the current hostname, and HTTP/HTTPS context. HTTPS is described as encryption rather than proof of legitimacy. A failed check is labeled **Not checked**. Existing keyboard-focus support, Escape dismissal, evidence reasons, and redirect information remain available. Future usability improvements include touchscreen activation, explicit copy-destination controls, screen-reader interaction testing, and richer explanations of lookalike domains. Redirect expansion remains separately opt-in because it contacts the destination.

**Current port correction:** `backend/main.py` now combines the browser and filing APIs on **8000**. Start it with `python -m uvicorn main:app --host 127.0.0.1 --port 8000` from `Extension_new/backend`, after installing `backend/requirements.txt`. Set both extension URLs to `http://127.0.0.1:8000`. `/health` reports filing-corpus health, `/api/health` reports browser engine health, and `/docs` lists both sets of routes. The earlier two-server instructions below describe the pre-unification arrangement and are superseded by this correction. Build the filing corpus from `email_detection` with `python -m data.load_all`; a second server is no longer required.

The toolbar now opens Extension_new's dark trust-score interface. Its **Open side panel** button opens the same workspace beside the current website. The narrow white WhatsApp popup belongs to the separate `email_detection` extension; load `Extension_new/extension` to use this interface.

### What users can do now

- Inspect page trust, signals, identity checks, recommendations, and history in the existing interface.
- Paste a message, investment claim, or link, or copy selected page text using **Use selected text**.
- Run **Check on device** without sending that input to a server. This result is separate from the current-page assessment.
- Explicitly verify an input against the filing-backed financial API, with a checkbox that clears when the input changes.
- Read the financial verdict, evidence reasons, matched filing and source link, field comparisons, and recommended actions. Evidence availability is not converted into a website trust score.
- Both browser analysis and financial verification default to port 8000 through the unified backend. Incompatible health responses display an explanation rather than NaN filings.

### Architecture and entry points

`extension/sidepanel/panel.html`, `panel.css`, and `panel.js` retain the original dark page-evidence interface. `workspace.js` adds selected-input controls to both views. `scripts/sync_popup.py` generates `extension/popup/popup.html` from the side-panel markup, preventing the two interfaces from drifting. Run it after changing the shared HTML. The manifest's `action.default_popup` selects that popup; `side_panel.default_path` retains the persistent panel.

`extension/shared/financial_verifier.js` validates analysis mode, endpoint, consent, input length, and response shape. The worker makes the explicit request, redacts matching phone/email patterns, omits credentials, rejects redirects, and applies bounded timeouts. Local mode disables verifier network calls; local-server mode allows only loopback. Result caching is ephemeral service-worker memory and is cleared on navigation, tab removal, or settings changes. Redaction is limited and does not remove every form of personal information.

### Setup and current reality

Reload the unpacked `Extension_new/extension` in Chrome and refresh page tabs. Install `backend/requirements.txt`, build the financial corpus from `email_detection` with `python -m data.load_all`, and start the unified API from `Extension_new/backend` with `python -m uvicorn main:app --host 127.0.0.1 --port 8000`. Choose Local server mode in extension settings and set both URLs to `http://127.0.0.1:8000`.

The financial integration currently supports selected or pasted text. It does not yet upload documents/screenshots or automatically apply filing verification to every chat message. On-device input checking is heuristic; an absence of findings is not proof that a claim is true. The service needs its own populated filing corpus. A broader UI does not by itself improve measured detection accuracy.

Validation: 185 Python tests pass; the browser VM harness and financial bridge harness pass. The latter checks consent/mode boundaries, redaction, response compatibility, and separation of evidence confidence from trust. A headless Chrome capture checks the static dark layout. Live unpacked-extension interaction and a real running financial API remain manual smoke-test work.

Next improvements should prioritize a representative accuracy corpus, allowlist ownership review, measured live-browser latency, accessible interaction testing, and document/image input with equally explicit consent. The existing personal exceptions remain scoped and expiring; community requests remain pending rather than automatically adding trusted websites.
