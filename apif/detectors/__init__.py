"""Detector package.

`warm_imports()` exists to fix a real race, and deleting it was a mistake worth
recording so it does not get deleted again.

Several packages here build their public namespace during import rather than
before it -- cv2 goes furthest and reassigns `sys.modules["cv2"]` partway
through its own bootstrap, and the scientific stack does lazy submodule loading.
Python's per-module import lock does not protect against that: a second thread
importing the same package finds a populated `sys.modules` entry, returns
immediately, and gets the half-built module. It surfaces as a nonsense
AttributeError in whichever thread lost the race -- observed in production as

    module 'cv2' has no attribute 'CascadeClassifier'

from /verify-link, the endpoint that overlaps the most worker threads, while
/verify and /analyze/video were fine.

The exposure is real and not theoretical: pipeline.analyze_text runs
trust_registry.analyze (pypdf) and market.analyze (yfinance -> pandas -> numpy)
concurrently under asyncio.gather, each in its own thread, and
coordination.analyze (sklearn -> scipy) is dispatched the same way.

Importing everything once at startup, on one thread, before any request can
arrive removes the race by construction. It also moves the first-request import
cost into boot, where it belongs. cv2, numpy and onnxruntime are not listed here
because detectors/video.py imports them at module scope for the same reason.
"""

from __future__ import annotations

import logging

log = logging.getLogger("apif.detectors")

# Imported for their side effect only. Each is otherwise imported lazily inside a
# function that runs in a worker thread.
_HEAVY = ("numpy", "pandas", "sklearn.feature_extraction.text",
          "sklearn.metrics.pairwise", "yfinance", "pypdf", "anthropic")

_warmed = False


def warm_imports() -> None:
    """Import the heavy stack once, at startup. Cheap no-op afterwards.

    Never raises. A package that is absent or broken must not stop the service
    from booting -- the detector that needs it will report itself unavailable,
    which is the same degradation path every other dependency uses.
    """
    global _warmed
    if _warmed:
        return

    import importlib

    for name in _HEAVY:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - warming is best-effort
            log.warning("warm import of %s failed: %s", name, exc)

    _warmed = True
