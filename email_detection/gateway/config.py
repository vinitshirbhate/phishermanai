"""Gateway configuration: config.yaml, overridable by environment variables.

Precedence, lowest to highest:

    dataclass defaults  ->  gateway/config.yaml  ->  PHAI_GW_* env vars  ->
    explicit CLI flags

Env override names are the field name uppercased with a PHAI_GW_ prefix, so
`port` is `PHAI_GW_PORT`. Lists are comma-separated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent
DEFAULT_CONFIG = GATEWAY_DIR / "config.yaml"

ENV_PREFIX = "PHAI_GW_"

RELAY_MAILDIR = "maildir"
RELAY_SMTP = "smtp"
RELAY_DISCARD = "discard"
RELAY_MODES = (RELAY_MAILDIR, RELAY_SMTP, RELAY_DISCARD)


@dataclass
class GatewayConfig:
    host: str = "127.0.0.1"
    port: int = 1025
    hostname: str = "phishermanai.gateway.local"

    engine_url: str = "http://127.0.0.1:8000"
    engine_timeout: float = 8.0

    relay_mode: str = RELAY_MAILDIR
    maildir_path: str = "gateway/maildir"
    relay_host: str = "127.0.0.1"
    relay_port: int = 25

    header_prefix: str = "X-PhishermanAI"
    subject_tagging: bool = True

    max_size_mb: int = 25
    rate_limit_per_min: int = 100

    recipient_allowlist: list[str] = field(default_factory=list)

    @property
    def max_size_bytes(self) -> int:
        return self.max_size_mb * 1024 * 1024

    @property
    def maildir_abspath(self) -> Path:
        path = Path(self.maildir_path)
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def verify_endpoint(self) -> str:
        return f"{self.engine_url.rstrip('/')}/verify/email"

    def is_public_binding(self) -> bool:
        """True when bound to something other than loopback."""
        return self.host not in ("127.0.0.1", "localhost", "::1")

    def recipient_allowed(self, address: str) -> bool:
        """Allowlist check for RCPT TO.

        Without this the gateway would accept mail for any recipient and relay
        it onward, which is the definition of an open relay. An empty allowlist
        therefore denies everything rather than allowing everything -- failing
        closed is correct here, because the failure mode is abuse by third
        parties rather than lost mail from a known sender.
        """
        if not address:
            return False
        candidate = address.strip().lower().strip("<>")
        for entry in self.recipient_allowlist:
            rule = entry.strip().lower()
            if not rule:
                continue
            if rule.startswith("@"):
                if candidate.endswith(rule):
                    return True
            elif candidate == rule:
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _coerce(raw: Any, target_type: Any) -> Any:
    if target_type is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if target_type is int:
        return int(raw)
    if target_type is float:
        return float(raw)
    if target_type is list or getattr(target_type, "__origin__", None) is list:
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return [x.strip() for x in str(raw).split(",") if x.strip()]
    return str(raw)


def load_config(path: str | Path | None = None, **overrides: Any) -> GatewayConfig:
    """Build a config from YAML, then environment, then explicit overrides."""
    config = GatewayConfig()

    config_path = Path(path) if path else DEFAULT_CONFIG
    if config_path.exists():
        try:
            import yaml
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - a broken config must not stop the gateway
            data = {}
        for f in fields(config):
            if f.name in data and data[f.name] is not None:
                setattr(config, f.name, _coerce(data[f.name], f.type if not isinstance(f.type, str) else type(getattr(config, f.name))))

    for f in fields(config):
        env_value = os.environ.get(ENV_PREFIX + f.name.upper())
        if env_value is not None:
            current = getattr(config, f.name)
            setattr(config, f.name, _coerce(env_value, type(current)))

    for key, value in overrides.items():
        if value is None:
            continue
        if any(f.name == key for f in fields(config)):
            current = getattr(config, key)
            setattr(config, key, _coerce(value, type(current)))

    if config.relay_mode not in RELAY_MODES:
        raise ValueError(f"relay_mode must be one of {RELAY_MODES}, got {config.relay_mode!r}")

    return config
