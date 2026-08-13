"""Detector package.

This used to expose `warm_imports()`, a lock that serialised the first
`import librosa` / `import torch` / `import transformers` because their lazy
submodule loading was not import-safe under concurrency -- two requests hitting
a cold process could race and one would fail with a spurious ImportError.

None of those packages are installed any more. ASR is an AssemblyAI call, the
voice spoof check is an Aurigin call, and the video detector is onnxruntime,
whose session is a plain lru_cache singleton with no such problem. The lock
guarded a race that no longer has anything to race.
"""