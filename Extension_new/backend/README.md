(The file `f:\SEBI-EX-2\backend_improved_@3\backend\README.md` exists, but contains only whitespace)
# Phisherman AI — Backend (optional)

Small FastAPI backend used by the browser extension for deeper on-device analysis. The backend is optional — the extension works with its offline rules and an optional cloud API.

Quick start
-----------
1. Create a Python virtualenv and activate it.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run the server locally: `uvicorn main:app --host 127.0.0.1 --port 8799`.

The extension defaults to on-device analysis. Select **Local server** in extension settings and set the backend URL to `http://127.0.0.1:8799` to enable this server. If unavailable, the immediate local assessment remains usable.

The backend defaults to pattern-only inference. Set `SCAMGATE_MAX_TIER=1` to permit local Ollama inference or `SCAMGATE_MAX_TIER=2` to permit configured cloud providers as well. Selecting local-server mode in the browser does not override a backend operator's provider configuration.

`POST /api/reviews` accepts a hostname and up to five short warning reasons, deduplicates submissions, and stores them as pending. No submission automatically changes the shared website allowlist.

Models and Ollama
-----------------
This repo can integrate with local model runtimes (Ollama) for richer analysis. See `models/README.md` for model build steps. Model artifacts are large and are ignored by `.gitignore`.

Developer notes
---------------
- Health check: `GET /health`
- API endpoints are defined in `main.py` and `api.py`.
- Tests: run `python -m pytest -q` from the repo root.

If you want, I can add a small `make` or `scripts/run_backend.sh` to simplify these steps.


