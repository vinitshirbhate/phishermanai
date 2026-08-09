from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "extension" / "contracts"
KEYS_DIR = CONTRACTS_DIR / "keys"
SIGNATURES_DIR = CONTRACTS_DIR / "signatures"
STATE_SIGNING_DIR = ROOT / "state" / "dev_signing"

TRUSTED_SIGNERS_PATH = CONTRACTS_DIR / "trusted_signers.json"
REVOCATIONS_PATH = CONTRACTS_DIR / "revocations.json"

DEFAULT_SIGNER_KEY_ID = "phisherman-sandbox-dev-2026-08"
DEFAULT_SIGNER_NAME = "Phisherman AI Sandbox Dev Signer (rotated 2026-08)"
DEFAULT_SIGNER_ALGORITHM = "ecdsa-p256-sha256"
DEFAULT_PRIVATE_KEY_PATH = STATE_SIGNING_DIR / "sandbox_dev_signer_2026_08.pem"
DEFAULT_PUBLIC_KEY_PATH = KEYS_DIR / "sandbox_dev_signer_pub.pem"

CONTRACT_FILES = {
    "extension_policy": {
        "path": CONTRACTS_DIR / "extension_policy.json",
        "signature_path": SIGNATURES_DIR / "extension_policy.sig.json",
    },
    "module_registry": {
        "path": CONTRACTS_DIR / "module_registry.json",
        "signature_path": SIGNATURES_DIR / "module_registry.sig.json",
    },
    "agent_registry": {
        "path": CONTRACTS_DIR / "agent_registry.json",
        "signature_path": SIGNATURES_DIR / "agent_registry.sig.json",
    },
}


def _load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _signer_fingerprint(public_key) -> str:
    public_bytes = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _sha256_bytes(public_bytes)


def _load_private_key(path: Path):
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_public_key(path: Path):
    return serialization.load_pem_public_key(path.read_bytes())


def _trusted_signers() -> dict[str, dict[str, Any]]:
    document = _load_json(TRUSTED_SIGNERS_PATH, default={"signers": []})
    signers = document.get("signers", [])
    return {entry["key_id"]: entry for entry in signers if isinstance(entry, dict) and entry.get("key_id")}


def _revocations() -> dict[str, Any]:
    return _load_json(
        REVOCATIONS_PATH,
        default={
            "version": 1,
            "last_reviewed": None,
            "revoked_key_ids": [],
            "revoked_contract_hashes": [],
            "revoked_contracts": [],
            "notes": [],
        },
    )


def bootstrap_dev_signing_materials() -> dict[str, str]:
    STATE_SIGNING_DIR.mkdir(parents=True, exist_ok=True)
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)

    key_created = False
    if not DEFAULT_PRIVATE_KEY_PATH.exists():
        private_key = ec.generate_private_key(ec.SECP256R1())
        DEFAULT_PRIVATE_KEY_PATH.write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        DEFAULT_PRIVATE_KEY_PATH.chmod(0o600)
        key_created = True

    private_key = _load_private_key(DEFAULT_PRIVATE_KEY_PATH)
    public_key = private_key.public_key()

    DEFAULT_PUBLIC_KEY_PATH.write_bytes(
        public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    fingerprint = _signer_fingerprint(public_key)
    trusted = _load_json(TRUSTED_SIGNERS_PATH, default={"version": 1, "signers": []})
    existing = next(
        (entry for entry in trusted.get("signers", []) if entry.get("key_id") == DEFAULT_SIGNER_KEY_ID),
        {},
    )
    signers = [entry for entry in trusted.get("signers", []) if entry.get("key_id") != DEFAULT_SIGNER_KEY_ID]
    signers.append(
        {
            "key_id": DEFAULT_SIGNER_KEY_ID,
            "name": DEFAULT_SIGNER_NAME,
            "algorithm": DEFAULT_SIGNER_ALGORITHM,
            "public_key_path": "keys/sandbox_dev_signer_pub.pem",
            "fingerprint_sha256": fingerprint,
            "status": "active",
            "scope": sorted(CONTRACT_FILES.keys()),
            "environment": "sandbox",
            "last_rotated": existing.get("last_rotated") if not key_created and existing else _utc_now(),
            "notes": "Dev-only signer for sandbox contract validation. Do not use for production distribution.",
        }
    )
    trusted["version"] = 1
    trusted["last_reviewed"] = _utc_now()
    trusted["signers"] = signers
    _dump_json(TRUSTED_SIGNERS_PATH, trusted)

    if not REVOCATIONS_PATH.exists():
        _dump_json(
            REVOCATIONS_PATH,
            {
                "version": 1,
                "last_reviewed": _utc_now(),
                "revoked_key_ids": [],
                "revoked_contract_hashes": [],
                "revoked_contracts": [],
                "notes": [],
            },
        )

    return {
        "key_id": DEFAULT_SIGNER_KEY_ID,
        "fingerprint_sha256": fingerprint,
        "private_key_path": str(DEFAULT_PRIVATE_KEY_PATH),
        "public_key_path": str(DEFAULT_PUBLIC_KEY_PATH),
    }


def sign_contracts(labels: list[str] | None = None) -> list[dict[str, Any]]:
    metadata = bootstrap_dev_signing_materials()
    private_key = _load_private_key(DEFAULT_PRIVATE_KEY_PATH)
    labels = labels or list(CONTRACT_FILES.keys())
    signed: list[dict[str, Any]] = []

    for label in labels:
        descriptor = CONTRACT_FILES[label]
        contract_path = descriptor["path"]
        signature_path = descriptor["signature_path"]
        payload = contract_path.read_bytes()
        payload_hash = _sha256_bytes(payload)
        signature_b64 = base64.b64encode(
            private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        ).decode("ascii")
        signature_doc = {
            "contract_label": label,
            "contract_path": contract_path.name,
            "algorithm": DEFAULT_SIGNER_ALGORITHM,
            "key_id": metadata["key_id"],
            "key_fingerprint_sha256": metadata["fingerprint_sha256"],
            "payload_sha256": payload_hash,
            "signature_b64": signature_b64,
            "signed_at": _utc_now(),
        }
        _dump_json(signature_path, signature_doc)
        signed.append(
            {
                "contract_label": label,
                "contract_path": str(contract_path),
                "signature_path": str(signature_path),
                "payload_sha256": payload_hash,
                "key_id": metadata["key_id"],
            }
        )

    return signed


def verify_contract(label: str) -> dict[str, Any]:
    descriptor = CONTRACT_FILES[label]
    contract_path = descriptor["path"]
    signature_path = descriptor["signature_path"]
    errors: list[str] = []

    if not contract_path.exists():
        return {
            "contract_label": label,
            "contract_path": str(contract_path),
            "signature_path": str(signature_path),
            "valid": False,
            "errors": [f"Missing contract file: {contract_path.name}"],
        }

    if not signature_path.exists():
        return {
            "contract_label": label,
            "contract_path": str(contract_path),
            "signature_path": str(signature_path),
            "valid": False,
            "errors": [f"Missing signature file: {signature_path.name}"],
        }

    payload = contract_path.read_bytes()
    payload_hash = _sha256_bytes(payload)
    signature_doc = _load_json(signature_path)
    trusted_signers = _trusted_signers()
    revocations = _revocations()

    if signature_doc.get("contract_label") != label:
        errors.append(f"Signature label mismatch for {label}.")
    if signature_doc.get("contract_path") != contract_path.name:
        errors.append(f"Signature path mismatch for {label}.")
    if signature_doc.get("payload_sha256") != payload_hash:
        errors.append(f"Signed payload hash mismatch for {label}.")

    key_id = signature_doc.get("key_id", "")
    signer = trusted_signers.get(key_id)
    if not signer:
        errors.append(f"Unknown signer key_id for {label}: {key_id}")
    else:
        if signer.get("status") != "active":
            errors.append(f"Signer {key_id} is not active.")
        if key_id in revocations.get("revoked_key_ids", []):
            errors.append(f"Signer {key_id} is revoked.")
        if label not in set(signer.get("scope", [])):
            errors.append(f"Signer {key_id} is not scoped for {label}.")
        public_key_rel = signer.get("public_key_path")
        if not public_key_rel:
            errors.append(f"Signer {key_id} is missing a public_key_path.")
        else:
            public_key_path = CONTRACTS_DIR / public_key_rel
            if not public_key_path.exists():
                errors.append(f"Signer public key missing: {public_key_rel}")
            else:
                public_key = _load_public_key(public_key_path)
                fingerprint = _signer_fingerprint(public_key)
                if signer.get("fingerprint_sha256") != fingerprint:
                    errors.append(f"Trusted signer fingerprint mismatch for {key_id}.")
                if signature_doc.get("key_fingerprint_sha256") != fingerprint:
                    errors.append(f"Signature fingerprint mismatch for {label}.")
                try:
                    public_key.verify(
                        base64.b64decode(signature_doc.get("signature_b64", "")),
                        payload,
                        ec.ECDSA(hashes.SHA256()),
                    )
                except (InvalidSignature, ValueError, TypeError):
                    errors.append(f"Signature verification failed for {label}.")

    if payload_hash in revocations.get("revoked_contract_hashes", []):
        errors.append(f"Contract hash revoked for {label}.")
    if contract_path.name in revocations.get("revoked_contracts", []):
        errors.append(f"Contract file revoked for {label}.")

    return {
        "contract_label": label,
        "contract_path": str(contract_path),
        "signature_path": str(signature_path),
        "payload_sha256": payload_hash,
        "key_id": key_id,
        "valid": not errors,
        "errors": errors,
    }


def contract_status_summary() -> dict[str, Any]:
    statuses = [verify_contract(label) for label in CONTRACT_FILES]
    overall_valid = all(status["valid"] for status in statuses)
    return {
        "overall_valid": overall_valid,
        "contracts": statuses,
        "trusted_signers": list(_trusted_signers().values()),
        "revocations": _revocations(),
    }
