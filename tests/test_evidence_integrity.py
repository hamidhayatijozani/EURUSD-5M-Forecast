from claimlab.evidence_store import generate_hash
from tests.evidence_helpers import sample_record


def test_hash_reproducible():
    row = sample_record()
    assert generate_hash(row) == generate_hash(row)


def test_hash_tamper_detected():
    row = sample_record()
    original_hash = row["evidence_hash"]
    row["forecast_direction"] = "DOWN"
    assert generate_hash(row) != original_hash


def test_snapshot_sha256_exists():
    assert sample_record()["snapshot_sha256"]
