# APIF — AI Propaganda Intelligence Framework

Backend for the SEBI hackathon brief in [fake_propaganda/plan.md](fake_propaganda/plan.md).

Two halves, deliberately:

- **Detection** — phishing/scam text, deepfake video, cloned voice, coordinated bot
  campaigns, and abnormal market activity, fused into one threat score.
- **Verification** — a registry of official SEBI / exchange / listed-company channels with
  lookalike-domain detection and digital-signature checks, so a *genuine* circular can be
  positively confirmed rather than merely "not flagged".

Diagrams of the system, request flow, and failure behaviour:
**[ARCHITECTURE.md](ARCHITECTURE.md)**.

---

## Setup

```powershell
python -m venv .venv --system-site-packages
.\.venv\Scripts\pip install -r requirements.txt
# torchaudio must match the globally installed torch (2.7.1), or its C extension
# fails to load with "OSError: [WinError 127]":
.\.venv\Scripts\pip install --index-url https://download.pytorch.org/whl/cpu torchaudio==2.7.1
```

Fill in [.env](.env) (already created, gitignored):

| Key | Required? | Effect if unset |
|---|---|---|
| `PHISHING_API_URL` | **yes** | Text scoring unavailable — the core signal |
| `ANTHROPIC_API_KEY` | recommended | No entity extraction, so **market correlation never fires** (no tickers) and explanations fall back to a template |
| `FIRECRAWL_API_KEY` | for ingestion | `/api/v1/ingest/run` returns an error; on-demand analysis still works |

Prerequisites already verified on this machine: `ffmpeg` at `C:\ffmpeg\bin\ffmpeg.exe`,
and `openai/whisper-small` in the local Hugging Face cache.

## Run

```powershell
# 1. The external phishing classifier must be up first (separate project):
#    it should answer GET http://127.0.0.1:8080/health
# 2. Then:
.\.venv\Scripts\python -m uvicorn apif.main:app --reload --port 8000
```

Interactive docs at <http://127.0.0.1:8000/docs>. `GET /health` reports every downstream;
`status: "degraded"` means an optional dependency is down, not that the service is broken.

```powershell
.\.venv\Scripts\python tests\test_engines.py    # 38 assertions, no network or models needed
```

---

## The main endpoint

`POST /api/v1/verify` takes any combination of text and one media file and routes by type.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/verify \
  -F "text=SEBI has approved a special dividend window for RELIANCE shareholders. Register at sebi-gov.in/dividend within 6 hours." \
  -F "source=https://sebi-gov.in/dividend"
```

```jsonc
{
  "risk_score": 0.78, "band": "High",
  "headline": "Likely market propaganda - driven by phishing/scam language",
  "signals": [
    {"name": "text_phishing",    "score": 0.999, "available": true,
     "summary": "Classifier: phishing (99.9% confidence)"},
    {"name": "source_untrusted", "score": 0.95,  "available": true,
     "summary": "Source impersonates sebi.gov.in (Securities and Exchange Board of India)"},
    {"name": "market_anomaly",   "score": 0.0,   "available": false,
     "error": "no tickers identified in the content"}
  ]
}
```

`available: false` means a detector was skipped or failed. Those are **excluded** from
scoring and the remaining weights renormalised — a detector that could not run must never
read as evidence of innocence.

### Full surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/verify` | One-click check — text, audio, video, or image |
| `POST` | `/api/v1/analyze/text` | Text only |
| `POST` | `/api/v1/analyze/audio` | Transcribe + synthetic-speech detection |
| `POST` | `/api/v1/analyze/video` | Frame deepfake + the whole audio pipeline |
| `GET`  | `/api/v1/registry/lookup?q=` | Is this domain / @handle / sender official? |
| `POST` | `/api/v1/registry/check-source` | Source vs. claimed issuer, + PDF signature check |
| `POST` | `/api/v1/ingest/run?wait=` | Firecrawl + NSE/BSE sweep |
| `GET`  | `/api/v1/feed` | Ingested content, filterable |
| `GET`  | `/api/v1/coordination` | Campaign analysis across stored chatter |
| `GET`  | `/api/v1/dashboard/broker` | Trending manipulated tickers, active campaigns |
| `GET`  | `/api/v1/dashboard/regulator` | Cross-platform rollup, most-impersonated issuers |

---

## How scoring works

Weighted mean over available signals (`text_phishing` .25, `voice_spoof` .20,
`video_deepfake` .20, `source_untrusted` .15, `coordination` .10, `market_anomaly` .10;
all tunable in [apif/config.py](apif/config.py)), then one override that encodes a fact a
linear model cannot:

1. **Registry-verified + digitally signed → capped at Low.** A signed SEBI circular is not
   "somewhat suspicious" because its wording scored high.

A second override once forced **Critical** when a voice both matched an enrolled official
*and* carried synthetic artefacts — a targeted clone. It was removed with the SpeechBrain
speaker-verification model: with no voiceprint comparison there is no `speaker_match` to
test, so the rule could never fire. Consequence worth knowing: the trusted-source cap is
now unopposed, so spoofed audio from a registry-verified signed source is held at Low.

---

## Deliberate limitations

Stated plainly because a regulatory tool should not overclaim:

- **The coordination engine is a heuristic** (TF-IDF similarity + burst timing), not the
  trained GNN in plan.md. There is no labelled bot dataset here; a GNN trained on nothing
  would be less trustworthy than a method you can explain to a regulator. Author and
  timestamp are recovered from the tweet URL — the handle sits in the path, and the status
  ID is a snowflake whose upper 41 bits are a millisecond timestamp.
- **PDF signature checking proves presence, not validity.** Verifying the certificate chain
  against India's CCA trust store is out of scope. Absence on a document claiming to be a
  mandated-signature circular is the actionable finding.
- **The video detector is a free Hugging Face Space.** Cold starts, ZeroGPU quota
  exhaustion, and downtime are normal; it soft-fails to `available: false` so a verdict is
  still produced from the other channels.
- **Voice spoof detection is a hosted API**, not a local model. It needs
  `AURIGIN_API_KEY` and network access; without either, the signal reports unavailable and
  fusion renormalizes. Uploads are capped at 5MB, so audio is transcoded to 16kHz mono MP3
  first — a 10-minute clip lands near 3.6MB. There is deliberately no fallback to the
  previous local checkpoint: it was uncalibrated (it scored genuine recordings as 100%
  spoof), and a confidently wrong answer is worse than an absent one.
- **No speaker verification.** The system can say audio is synthetic, but not *whose*
  voice was cloned. Restoring `speechbrain/spkrec-ecapa-voxceleb` is what would bring back
  the cloned-official verdict.
- **NSE blocks programmatic clients.** The cookie-priming workaround in
  [apif/ingest/exchanges.py](apif/ingest/exchanges.py) works today and may break whenever
  NSE changes its edge config. `yfinance` carries the demo-critical market path.
- **CPU-only torch.** Uploads over `max_media_seconds` (default 120s) are rejected with
  **413** rather than returned as an unscored `Low` verdict — a green band on content
  nothing examined is the worst failure mode this system could have.

## Layout

```
apif/
  main.py          FastAPI app, /health, 413 handler
  config.py        all tunables + .env loading
  schemas.py       Signal / Verdict — the only types crossing module boundaries
  compat.py        inspect.getmodule patch for lazy ML imports; must load first
  pipeline.py      orchestration: routing, concurrency, fan-out
  detectors/       text_phishing, llm_analyst, asr, voice, video, media
  engines/         fusion, trust_registry, market, coordination
  ingest/          firecrawl, exchanges, store (SQLite)
  data/            trusted_sources.json
tests/             test_engines.py
```

The original scripts under [deepfake_detection/](deepfake_detection/) and
[fake_propaganda/](fake_propaganda/) are left runnable as references; `apif/` contains the
refactored versions. `verify_voice.py` in particular is the baseline the voice detector is
validated against — both report similarity ≈ 0.85 and 0.00% spoof on the bundled samples.
