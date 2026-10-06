import json

import pytest

import claimlab.registry as registry


def test_registry_cryptographic_integrity():
    """The checked-in claims registry must match its canonical lock."""
    assert registry.assert_locked() == registry.locked_hash()


def test_registry_tampering_is_rejected(tmp_path, monkeypatch):
    """A changed claim must fail the lock before verdict evaluation."""
    original = registry.load_registry()
    tampered = json.loads(json.dumps(original))
    tampered["claims"][0]["threshold"] = 999.0

    registry_path = tmp_path / "claims.json"
    lock_path = tmp_path / "registry.lock"
    registry_path.write_text(
        json.dumps(tampered, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lock_path.write_text(registry.registry_hash() + "\n", encoding="utf-8")

    monkeypatch.setattr(registry, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(registry, "LOCK_PATH", lock_path)

    # Rebuild the lock from the untampered registry to model an existing
    # trusted lock, then replace the tampered file without changing the lock.
    lock_path.write_text(
        registry.registry_hash() + "\n", encoding="utf-8"
    )
    original_canonical = json.dumps(
        original, sort_keys=True, separators=(",", ":")
    )
    lock_path.write_text(
        __import__("hashlib").sha256(
            original_canonical.encode("utf-8")
        ).hexdigest()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="REGISTRY LOCK MISMATCH"):
        registry.assert_locked()
