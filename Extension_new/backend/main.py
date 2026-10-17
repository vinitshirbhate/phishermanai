"""Unified browser and financial API: uvicorn main:app --port 8000.

The financial package is loaded under a private name because both projects
have an `api` module. Their original endpoints remain available unchanged.
"""
from importlib import import_module, util
from pathlib import Path
import sys

from fastapi import APIRouter
from api import app as browser_app

FINANCIAL_ROOT = Path(__file__).resolve().parents[2] / 'email_detection'
if not FINANCIAL_ROOT.is_dir():
    raise RuntimeError('Unified API requires the sibling email_detection directory.')
sys.path.append(str(FINANCIAL_ROOT))
PACKAGE = '_phisherman_financial_api'
if PACKAGE not in sys.modules:
    spec = util.spec_from_file_location(
        PACKAGE, FINANCIAL_ROOT / 'api' / '__init__.py',
        submodule_search_locations=[str(FINANCIAL_ROOT / 'api')],
    )
    package = util.module_from_spec(spec)
    sys.modules[PACKAGE] = package
    spec.loader.exec_module(package)
try:
    app = import_module(PACKAGE + '.main').app
except ModuleNotFoundError as error:
    raise RuntimeError('Install the unified dependencies: python -m pip install -r requirements.txt') from error

browser_routes = APIRouter()
browser_routes.routes.extend(route for route in browser_app.router.routes
                             if getattr(route, 'path', '') not in {'/health', '/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc'})
app.include_router(browser_routes)
app.title = 'PhishermanAI — Browser and Financial Verification'
app.version = '6.3.0'
from pdf_check import router as pdf_router
app.include_router(pdf_router)
# /health reports the financial corpus; /api/health exposes browser engine health.
app.add_api_route('/api/health', next(route.endpoint for route in browser_app.router.routes
                                    if getattr(route, 'path', '') == '/health'), methods=['GET'])
