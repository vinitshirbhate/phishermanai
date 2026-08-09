"""APIF — AI Propaganda Intelligence Framework.

Detects AI-generated market propaganda (phishing text, deepfake video, cloned voice,
coordinated bot campaigns) and verifies that genuine SEBI/exchange/company
communications are authentic.
"""

# MUST be first: patches inspect.getmodule before speechbrain/transformers load.
from . import compat as _compat  # noqa: F401  (import for side effect)

__version__ = "0.1.0"
