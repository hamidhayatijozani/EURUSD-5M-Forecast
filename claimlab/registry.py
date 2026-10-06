"""Canonical ClaimLab registry and deterministic lock."""
import hashlib
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).with_name("claims.json")
LOCK_PATH = Path(__file__).with_name("registry.lock")


def load_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def registry_hash():
    obj = load_registry()
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def locked_hash():
    return LOCK_PATH.read_text(encoding="utf-8").strip()


def assert_locked():
    expected = locked_hash()
    actual = registry_hash()
    if actual != expected:
        raise RuntimeError(
            f"CLAIMLAB REGISTRY LOCK MISMATCH: expected {expected}, got {actual}"
        )
    if load_registry().get("status") != "LOCKED":
        raise RuntimeError("CLAIMLAB registry is not LOCKED")
    return actual
