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
    firecrawl_api_key: str = ""
    phishing_api_url: str = "http://127.0.0.1:8080"
    aurigin_api_key: str = ""
    aurigin_base_url: str = "https://api.aurigin.ai/v1"
    # The /predict endpoint rejects uploads over 5MB. Audio is transcoded to 16kHz mono
    # MP3 before upload, which keeps a 10-minute clip near 3.6MB.
    aurigin_max_upload_mb: float = 5.0

    # --- local models ---
    whisper_model: str = "openai/whisper-small"
    ffmpeg_path: str = "ffmpeg"

    # --- remote video deepfake Space ---
    video_space_id: str = "KoreaPeter/DeepFake-Video-Detection"
    video_space_timeout: float = 180.0

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
