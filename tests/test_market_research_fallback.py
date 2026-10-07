from datetime import datetime, timedelta, timezone

from scripts.run_market_research import run


def test_market_research_uses_explicit_eurusd_only_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    rows = [(start + timedelta(minutes=5 * i), 1.1 + i * 0.00001) for i in range(30)]

    def unavailable_cross_asset():
        raise RuntimeError("no fresh common auxiliary candles")

    result = run(data_loader=unavailable_cross_asset, eurusd_loader=lambda symbol: rows)
    assert result["research_status"] == "PARTIAL_DATA"
    assert result["metrics_computed"] is True
    assert result["auxiliary_cross_asset_status"] == "DATA_UNAVAILABLE"
    assert result["strategies"]["BASELINE"]["n"] > 0
    assert result["strategies"]["EXP-006"]["n"] > 0
    assert result["strategies"]["EXP-007"]["status"] == "DATA_UNAVAILABLE"
    assert result["strategies"]["COMBINATION"]["status"] == "DATA_UNAVAILABLE"
    assert (tmp_path / "research/results/latest.json").exists()
