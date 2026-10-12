from scripts.audit_decision_evidence import audit
from engine.forecast_evidence import build_decision_evidence


def sample_evidence():
    return build_decision_evidence(
        candle_times=["2026-10-12T10:00:00+00:00", "2026-10-12T10:01:00+00:00"],
        series={"EURUSD": [1.1, 1.2]},
        ohlc={"EURUSD": [(1.0, 1.2, 0.9, 1.1), (1.1, 1.3, 1.0, 1.2)]},
        source_candle_ts="2026-10-12T10:01:00+00:00",
        feature_cutoff_at="2026-10-12T10:01:00+00:00",
        issued_at="2026-10-12T10:02:00+00:00",
        target_ts="2026-10-12T10:06:00+00:00",
        config_hash="cfg",
        model_components={"signal_name": "TEST", "adjusted_score": 0.1, "algorithms": []},
        external_context={"directional_sources_available": 0},
    )


def test_audit_reports_missing_historical_evidence_without_reconstruction():
    result = audit([{"prediction_id": "old", "status": "RESOLVED"}])
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["missing_evidence_rows"] == 1
    assert result["valid_evidence_rows"] == 0


def test_audit_counts_valid_snapshot_components():
    evidence = sample_evidence()
    result = audit([{
        "prediction_id": "new", "status": "RESOLVED",
        "decision_evidence": evidence,
        "decision_evidence_sha256": evidence["snapshot_sha256"],
    }])
    assert result["status"] == "AUDITED"
    assert result["valid_evidence_rows"] == 1
    assert result["component_presence_counts"]["algorithms"] == 1


def test_audit_detects_tampering_and_hash_reference_mismatch():
    evidence = sample_evidence()
    evidence["external_context"]["directional_sources_available"] = 3
    result = audit([{
        "prediction_id": "tampered", "status": "RESOLVED",
        "decision_evidence": evidence,
        "decision_evidence_sha256": evidence["snapshot_sha256"],
    }])
    assert result["status"] == "INTEGRITY_FAILURE"
    assert result["invalid_evidence_rows"] == 1
