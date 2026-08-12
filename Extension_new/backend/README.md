(The file `f:\SEBI-EX-2\backend_improved_@3\backend\README.md` exists, but contains only whitespace)
# Phisherman AI — Backend (optional)

Small FastAPI backend used by the browser extension for deeper on-device analysis. The backend is optional — the extension works with its offline rules and an optional cloud API.

Quick start
-----------
1. Create a Python virtualenv and activate it.
2. Install dependencies: `pip install -r requirements.txt`.
3. Run the server locally: `uvicorn main:app --host 127.0.0.1 --port 8799`.

The extension will detect a backend on `localhost:8799` automatically. If the backend is not available, the extension falls back to offline checks.

Models and Ollama
-----------------
This repo can integrate with local model runtimes (Ollama) for richer analysis. See `models/README.md` for model build steps. Model artifacts are large and are ignored by `.gitignore`.

Developer notes
---------------
- Health check: `GET /health`
- API endpoints are defined in `main.py` and `api.py`.
- Tests: run `python -m pytest -q` from the repo root.

If you want, I can add a small `make` or `scripts/run_backend.sh` to simplify these steps.


