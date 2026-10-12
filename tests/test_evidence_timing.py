import pytest
from engine.evidence_contract import build_record, validate_temporal_contract, TemporalContractError


def test_cutoff_before_issue_before_target():
    record = build_record(feature_cutoff_at="2026-10-12T02:24:59Z",
                          issued_at="2026-10-12T02:25:00Z",
                          target_ts="2026-10-12T02:30:00Z")
    assert validate_temporal_contract(record)


def test_equal_cutoff_and_issue_rejected():
    record = {"feature_cutoff_at": "2026-10-12T02:25:00Z",
              "issued_at": "2026-10-12T02:25:00Z",
              "target_ts": "2026-10-12T02:30:00Z"}
    with pytest.raises(TemporalContractError):
        validate_temporal_contract(record)


def test_future_data_rejected():
    record = {"feature_cutoff_at": "2026-10-12T02:26:00Z",
              "issued_at": "2026-10-12T02:25:00Z",
              "target_ts": "2026-10-12T02:30:00Z"}
    with pytest.raises(TemporalContractError):
        validate_temporal_contract(record)


def test_timezone_is_required():
    with pytest.raises(TemporalContractError):
        validate_temporal_contract({"feature_cutoff_at": "2026-10-12T02:24:59",
                                    "issued_at": "2026-10-12T02:25:00Z",
                                    "target_ts": "2026-10-12T02:30:00Z"})
