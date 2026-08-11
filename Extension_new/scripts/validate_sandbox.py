from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.contract_security import bootstrap_dev_signing_materials, contract_status_summary, sign_contracts

EXTENSION = ROOT / "extension"
MANIFEST_PATH = EXTENSION / "manifest.json"
POLICY_PATH = EXTENSION / "contracts" / "extension_policy.json"
MODULES_PATH = EXTENSION / "contracts" / "module_registry.json"
AGENTS_PATH = EXTENSION / "contracts" / "agent_registry.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def canonical_digest(record: dict) -> str:
    body = {k: v for k, v in record.items() if k != "integrity_sha256"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def rewrite_hashes(items: list[dict]) -> list[dict]:
    rewritten = []
    for item in items:
        fresh = dict(item)
        fresh["integrity_sha256"] = canonical_digest(fresh)
        rewritten.append(fresh)
    return rewritten


def validate_integrity(items: list[dict], label: str) -> list[str]:
    errors: list[str] = []
    for item in items:
        expected = canonical_digest(item)
        actual = item.get("integrity_sha256")
        if actual != expected:
            errors.append(f"{label} {item.get('id')} has stale integrity_sha256")
    return errors


def validate() -> list[str]:
    manifest = load_json(MANIFEST_PATH)
    policy = load_json(POLICY_PATH)
    modules = load_json(MODULES_PATH)
    agents = load_json(AGENTS_PATH)

    errors: list[str] = []

    allowed_permissions = set(policy["allowed_permissions"])
    allowed_hosts = set(policy["allowed_host_permissions"])
    allowed_capabilities = set(policy["allowed_capabilities"])

    manifest_permissions = set(manifest.get("permissions", []))
    manifest_hosts = set(manifest.get("host_permissions", []))

    extra_permissions = sorted(manifest_permissions - allowed_permissions)
    extra_hosts = sorted(manifest_hosts - allowed_hosts)

    if extra_permissions:
        errors.append(f"manifest.json requests permissions not in policy: {extra_permissions}")
    if extra_hosts:
        errors.append(f"manifest.json requests hosts not in policy: {extra_hosts}")

    for module in modules:
        missing = {"id", "name", "capabilities", "approval_required", "data_classes"} - set(module)
        if missing:
            errors.append(f"module {module.get('id')} missing fields: {sorted(missing)}")
        bad_caps = sorted(set(module.get("capabilities", [])) - allowed_capabilities)
        if bad_caps:
            errors.append(f"module {module.get('id')} uses unknown capabilities: {bad_caps}")

    for agent in agents:
        missing = {"id", "name", "capabilities", "approval_required", "side_effects"} - set(agent)
        if missing:
            errors.append(f"agent {agent.get('id')} missing fields: {sorted(missing)}")
        bad_caps = sorted(set(agent.get("capabilities", [])) - allowed_capabilities)
        if bad_caps:
            errors.append(f"agent {agent.get('id')} uses unknown capabilities: {bad_caps}")
        if agent.get("side_effects") and not agent.get("approval_required"):
            errors.append(f"agent {agent.get('id')} has side effects but approval_required=false")

    errors.extend(validate_integrity(modules, "module"))
    errors.extend(validate_integrity(agents, "agent"))

    contract_status = contract_status_summary()
    for status in contract_status["contracts"]:
        if not status["valid"]:
            errors.extend(f"signature {status['contract_label']}: {error}" for error in status["errors"])
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rewrite", action="store_true", help="Rewrite integrity_sha256 for module and agent contracts.")
    parser.add_argument("--bootstrap-signing", action="store_true", help="Create an isolated dev-only signing keypair for sandbox contract validation.")
    parser.add_argument("--sign", action="store_true", help="Sign policy, module, and agent contract files with the local sandbox dev signer.")
    args = parser.parse_args()

    if args.rewrite:
        dump_json(MODULES_PATH, rewrite_hashes(load_json(MODULES_PATH)))
        dump_json(AGENTS_PATH, rewrite_hashes(load_json(AGENTS_PATH)))

    if args.bootstrap_signing or args.sign:
        bootstrap_dev_signing_materials()

    if args.sign:
        sign_contracts()

    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("SANDBOX_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
