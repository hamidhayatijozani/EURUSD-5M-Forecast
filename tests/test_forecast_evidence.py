from datetime import datetime, timedelta, timezone

import pytest

from engine.forecast_evidence import build_decision_evidence, verify_decision_evidence


def fixture():
    start = datetime(2026, 10, 12, 10, 0, tzinfo=timezone.utc)
    times = [start + timedelta(minutes=i) for i in range(3)]
    return dict(
        candle_times=times,
        series={"EURUSD": [1.1, 1.2, 1.3], "GBPUSD": [1.3, 1.4, 1.5]},
        ohlc={"open": [1.0, 1.1, 1.2], "high": [1.2, 1.3, 1.4],
              "low": [0.9, 1.0, 1.1], "close": [1.1, 1.2, 1.3]},
        source_candle_ts=times[-1],
        feature_cutoff_at=times[-1],
        issued_at=times[-1] + timedelta(minutes=1),
        target_ts=times[-1] + timedelta(minutes=5),
        config_hash="cfg-sha",
        model_components={"ensemble_score": 0.2, "algorithms": [{"name": "MOM_2", "score": 0.1}]},
        external_context={"directional_sources_available": 0, "power_score": 0.0},
    )


def test_snapshot_is_timestamped_aligned_and_hashed():
    evidence = build_decision_evidence(**fixture())
    assert evidence["schema"] == "claimlab.forecast_decision_evidence.v1"
    assert evidence["future_input_excluded"] is True
    assert evidence["candle_open_times"][-1] == evidence["source_candle_ts"]
    assert len(evidence["series_close_inputs"]["EURUSD"]) == 3
    assert len(evidence["snapshot_sha256"]) == 64
    assert verify_decision_evidence(evidence) is True


def test_rejects_future_or_misaligned_candle():
    args = fixture()
    args["candle_times"] = args["candle_times"] + [args["source_candle_ts"] + timedelta(minutes=1)]
    args["series"] = {"EURUSD": [1, 2, 3, 4], "GBPUSD": [1, 2, 3, 4]}
    args["ohlc"] = {"close": [1, 2, 3, 4]}
    with pytest.raises(ValueError, match="SOURCE_CANDLE"):
        build_decision_evidence(**args)


def test_rejects_mismatched_series_lengths():
    args = fixture()
    args["series"]["EURUSD"] = [1.1]
    with pytest.raises(ValueError, match="SERIES_LENGTH_MISMATCH"):
        build_decision_evidence(**args)


def test_rejects_issue_time_before_candle_close():
    args = fixture()
    args["issued_at"] = args["source_candle_ts"] + timedelta(seconds=20)
    with pytest.raises(ValueError, match="ISSUED_BEFORE"):
        build_decision_evidence(**args)


def test_rejects_cutoff_equal_to_issue_time():
    args = fixture()
    args["feature_cutoff_at"] = args["issued_at"]
    with pytest.raises(ValueError, match="TEMPORAL_CONTRACT"):
        build_decision_evidence(**args)


def test_rejects_issue_at_or_after_target():
    args = fixture()
    args["issued_at"] = args["target_ts"]
    with pytest.raises(ValueError, match="TEMPORAL_CONTRACT"):
        build_decision_evidence(**args)


def test_evidence_tampering_is_detected():
    evidence = build_decision_evidence(**fixture())
    evidence["model_components"]["adjusted_score"] = 999
    assert verify_decision_evidence(evidence) is False


def test_ohlc_tuple_rows_are_preserved_as_numeric_rows():
    args = fixture()
    args["ohlc"] = {"EURUSD": [(1.0, 1.2, 0.9, 1.1), (1.1, 1.3, 1.0, 1.2), (1.2, 1.4, 1.1, 1.3)]}
    evidence = build_decision_evidence(**args)
    assert evidence["eurusd_ohlc_inputs"][0]["values"][-1] == [1.2, 1.4, 1.1, 1.3]
