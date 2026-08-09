"""Detector package.

`warm_imports()` exists to fix a real race. On a cold process, two concurrent requests
can reach `import librosa` / `import transformers` in different worker threads at the
same moment. Those packages pull in numba and torch extensions whose lazy submodule
loading is not import-safe under concurrency, which surfaces as a spurious
`ImportError: cannot import name ...` in whichever thread loses the race -- the other
thread succeeds, so the failure looks random.

Serialising just the first import removes it, without holding the lock across inference.

Originally this also covered the spoof detector racing ASR within a single request. The
spoof detector is now a network call and imports none of this stack, so ASR is the only
caller -- the lock now guards concurrent *requests* rather than concurrent detectors.
"""

import threading

_IMPORT_LOCK = threading.Lock()
_warmed = False


def warm_imports() -> None:
    """Import the heavy audio/ML stack once, under a lock. Cheap no-op afterwards."""
    global _warmed
    if _warmed:
        return
    with _IMPORT_LOCK:
        if _warmed:
            return
        import librosa  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401

        _warmed = True
