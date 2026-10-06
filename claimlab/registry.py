"""Canonical ClaimLab registry and deterministic lock hash."""
import hashlib, json
from pathlib import Path

REGISTRY_PATH=Path(__file__).with_name("claims.json")

def load_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

def registry_hash():
    raw=REGISTRY_PATH.read_text(encoding="utf-8")
    obj=json.loads(raw)
    canonical=json.dumps(obj,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
