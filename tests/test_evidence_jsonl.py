import json
import pytest
from claimlab.evidence_store import JsonLedger
from tests.evidence_helpers import sample_record


def test_jsonl_append_only(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = JsonLedger(path)
    ledger.append(sample_record())
    assert len(path.read_text().splitlines()) == 1
    with pytest.raises(ValueError, match="DUPLICATE_PREDICTION_ID"):
        ledger.append(sample_record())
    assert len(path.read_text().splitlines()) == 1


def test_jsonl_record_contains_snapshot():
    row = sample_record()
    assert row["decision_snapshot"] is not None
    assert row["snapshot_sha256"] == row["decision_snapshot"]["snapshot_sha256"]


def test_jsonl_record_contains_hash():
    row = sample_record()
    assert len(row["evidence_hash"]) == 64


def test_jsonl_tampering_fails_verification(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = JsonLedger(path)
    ledger.append(sample_record())
    row = json.loads(path.read_text())
    row["forecast_direction"] = "DOWN"
    path.write_text(json.dumps(row) + "\n")
    assert ledger.verify() is False
