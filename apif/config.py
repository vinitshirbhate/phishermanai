"""Central configuration. Everything tunable lives here, nothing is hardcoded in logic."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root — model directories and sample media are resolved relative to this so
# the service works regardless of the working directory uvicorn is launched from.
ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- external services ---
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai"
    openrouter_model: str = "gpt-4o-mini"
    firecrawl_api_key: str = ""
    phishing_api_url: str = "http://127.0.0.1:8080"
    aurigin_api_key: str = ""
    aurigin_base_url: str = "https://api.aurigin.ai/v1"
    # The /predict endpoint rejects uploads over 5MB. Audio is transcoded to 16kHz mono
    # MP3 before upload, which keeps a 10-minute clip near 3.6MB.
    aurigin_max_upload_mb: float = 5.0
    # Speech-to-text. Replaced a local whisper-small; without this key the audio
    # path still runs the spoof check, it just has no transcript to classify.
    assemblyai_api_key: str = ""

    # --- ffmpeg ---
    # Empty means "use the binary bundled in the imageio-ffmpeg wheel", which is
    # what makes `pip install -r requirements.txt` the whole setup. Set a path
    # only to override it with a host build.
    ffmpeg_path: str = ""

    # --- video deepfake (local ONNX, see detectors/video.py) ---
    video_model_path: Path = ROOT / "apif/data/models/ffpp_efficientnet_b0.onnx"
    # Both mirror the training config in the original checkpoint; changing them
    # moves the model out of the distribution it was fitted on.
    video_frames_per_clip: int = 16
    # Inference is cheap enough that this barely moves memory (batch 8 vs 1
    # measured under 2MB apart); video decoding is what costs.
    video_batch_size: int = 8
    # On a shared vCPU, extra ONNX threads cost more in contention than they win.
    onnx_intra_op_threads: int = 1
    # Ignore faces smaller than this fraction of the frame's shorter side --
    # upscaling a 30px box to 224px feeds the model interpolation artefacts.
    video_min_face_ratio: float = 0.05
    # Fraction of scored frames averaged for the clip score. See detectors/video.py
    # for why this is a top-k mean rather than a plain mean.
    video_topk_fraction: float = 0.25

    # --- storage ---
    database_url: str = "sqlite:///./apif.db"
    upload_dir: Path = ROOT / "apif/data/uploads"
    trusted_sources_path: Path = ROOT / "apif/data/trusted_sources.json"

    # --- detector thresholds ---
    # The spoof service returns a calibrated verdict ("bonafide"/"spoofed") alongside its
    # score, so the voice detector trusts that label rather than thresholding the score
    # itself. No local label-polarity setting to get wrong.
    sample_rate: int = 16000
    # CPU-only torch: cap uploads so a demo never hangs on a long clip.
    max_media_seconds: float = 120.0

    # --- risk fusion weights (see engines/fusion.py) ---
    weight_text_phishing: float = 0.25
    weight_voice_spoof: float = 0.20
    weight_video_deepfake: float = 0.20
    weight_source_untrusted: float = 0.15
    weight_coordination: float = 0.10
    weight_market_anomaly: float = 0.10

    band_medium: float = 0.30
    band_high: float = 0.60
    band_critical: float = 0.80


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached so the .env is parsed once per process."""
    return Settings()
