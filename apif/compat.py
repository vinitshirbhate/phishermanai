"""Import-order-sensitive interpreter patches. Must be imported before transformers —
apif/__init__.py does this on the first line."""

import inspect

# Lazy-module placeholders in the ML stack raise ImportError from __getattr__ instead of
# AttributeError. inspect.getmodule() relies on hasattr(module, '__file__') only ever
# raising AttributeError, so any inspect call that scans sys.modules while such a
# placeholder is present (e.g. transformers importing torchvision) crashes with an
# unrelated "No module named ..." error. Patch getmodule to swallow it.
#
# FastAPI makes this worse than it is in a script: it calls inspect heavily while
# building routes from type hints, so an unpatched import blows up at startup.
#
# This originally worked around SpeechBrain 1.0's LazyModule (k2/flair/fairseq). That
# dependency is gone, but transformers hits the same class of failure, so the patch
# stays -- it is idempotent and costs nothing.
_original_getmodule = inspect.getmodule


def _safe_getmodule(*args, **kwargs):
    try:
        return _original_getmodule(*args, **kwargs)
    except Exception:
        return None


def apply() -> None:
    # Idempotent: re-importing this module must not stack patches.
    if getattr(inspect.getmodule, "_apif_patched", False):
        return
    _safe_getmodule._apif_patched = True
    inspect.getmodule = _safe_getmodule


apply()
