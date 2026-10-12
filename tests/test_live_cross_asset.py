from scripts.live_minute_loop import (
    CROSS_ASSET_CANDIDATES,
    CROSS_ASSET_LEDGER_PATH,
    CROSS_ASSET_CONTRACT_VERSION_V2,
    _read_cross_asset_ledger,
    append_cross_asset_observations,
    cross_asset_candidates,
    cross_asset_candidates_v2,
)


def test_live_cross_asset_candidates_require_all_aligned_sources():
    prices = [1.1 + i * 0.0001 for i in range(40)]
    partial = {"EURUSD": prices, "GBPUSD": prices, "USDJPY": prices}
    positions, status = cross_asset_candidates(partial)
    assert status == "READY_PARTIAL"
    assert positions["LIVE1M_NO_TRADE"] == 0
    assert positions["LIVE1M_EUR_GBP_DIVERGENCE_Z15"] is not None
    assert positions["LIVE1M_DXY_INVERSE_3M"] is None
    assert positions["LIVE1M_DOLLAR_CONSENSUS_3M"] is None


def test_live_cross_asset_candidates_use_past_aligned_series():
    series = {
        "EURUSD": [1.1 + i * 0.0001 for i in range(40)],
        "GBPUSD": [1.3 + i * 0.0002 for i in range(40)],
        "USDJPY": [150.0 - i * 0.01 for i in range(40)],
        "DXY": [100.0 - i * 0.01 for i in range(40)],
    }
    positions, status = cross_asset_candidates(series)
    assert status == "READY"
    assert positions["LIVE1M_DOLLAR_CONSENSUS_3M"] == 1
    assert positions["LIVE1M_DXY_INVERSE_3M"] == 1
    assert positions["LIVE1M_EURUSD_MOMENTUM_CONFIRMED"] == 1


def test_live_cross_asset_ledger_is_hash_chained_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "scripts.live_minute_loop.CROSS_ASSET_LEDGER_PATH",
        tmp_path / "cross_asset_live_observations.jsonl",
    )
    prediction = {
        "prediction_id": "test-prediction-1",
        "prediction_ts": "2026-10-12T12:01:00+00:00",
        "target_at": "2026-10-12T12:06:00+00:00",
        "provider": "Yahoo",
        "source_candle_ts": "2026-10-12T12:00:00+00:00",
        "observed_at": "2026-10-12T12:01:30+00:00",
        "data_age_seconds": 30.0,
        "freshness_status": "FRESH",
        "cross_asset_status": "READY",
        "cross_asset_candidates": {
            "LIVE1M_NO_TRADE": 0,
            "LIVE1M_DOLLAR_CONSENSUS_3M": 1,
            "LIVE1M_COMPOSITE_Z15": None,
        },
        "cross_asset_status_v2": "READY",
        "cross_asset_available_symbols": ["GBPUSD", "USDJPY"],
        "cross_asset_candidates_v2": {
            "LIVE1M2_NO_TRADE": 0,
            "LIVE1M2_USDJPY_INVERSE_3M": -1,
        },
    }
    count = append_cross_asset_observations(
        prediction, 0.0001, "2026-10-12T12:06:00+00:00", "abc123"
    )
    assert count == 4
    assert append_cross_asset_observations(
        prediction, 0.0001, "2026-10-12T12:06:00+00:00", "abc123"
    ) == 0
    rows, last_hash = _read_cross_asset_ledger()
    assert len(rows) == 4
    assert rows[0]["candidate_id"] == "LIVE1M_NO_TRADE"
    assert rows[0]["net_return"] == 0.0
    assert rows[1]["net_return"] == 0.00008
    assert rows[-1]["contract_version"] == CROSS_ASSET_CONTRACT_VERSION_V2
    assert rows[-1]["candidate_id"] == "LIVE1M2_USDJPY_INVERSE_3M"
    assert rows[-1]["record_hash"] == last_hash


def test_cross_asset_candidate_availability_is_per_candidate():
    eurusd = [1.1 + i * 0.0001 for i in range(40)]
    dxy = [100.0 - i * 0.01 for i in range(40)]
    positions, status = cross_asset_candidates({"EURUSD": eurusd, "DXY": dxy})
    assert status == "READY_PARTIAL"
    assert positions["LIVE1M_DXY_INVERSE_3M"] == 1
    assert positions["LIVE1M_DOLLAR_CONSENSUS_3M"] is None
    assert positions["LIVE1M_EUR_GBP_DIVERGENCE_Z15"] is None
    assert positions["LIVE1M_NO_TRADE"] == 0
