from datetime import datetime, timezone

from engine import market_providers as mp


def test_oanda_parser_keeps_only_complete_mid_candles():
    payload = {"candles": [
        {"time": "2026-10-12T12:00:00.000000000Z", "complete": True,
         "volume": 10, "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.15"}},
        {"time": "2026-10-12T12:01:00.000000000Z", "complete": False,
         "volume": 5, "mid": {"o": "1.1", "h": "1.2", "l": "1.0", "c": "1.16"}},
    ]}
    result = mp._parse_oanda(payload)
    assert len(result["timestamp"]) == 1
    assert result["indicators"]["quote"][0]["close"] == [1.15]


def test_twelvedata_parser_orders_candles_oldest_first():
    payload = {"values": [
        {"datetime": "2026-10-12 12:01:00", "open": "1.2", "high": "1.3",
         "low": "1.1", "close": "1.25"},
        {"datetime": "2026-10-12 12:00:00", "open": "1.1", "high": "1.2",
         "low": "1.0", "close": "1.15"},
    ]}
    result = mp._parse_twelvedata(payload)
    assert result["timestamp"] == sorted(result["timestamp"])
    assert result["indicators"]["quote"][0]["close"] == [1.15, 1.25]


def test_provider_failover_skips_unavailable_oanda_then_uses_yahoo(monkeypatch):
    monkeypatch.setenv("LIVE_FEED_PROVIDERS", "oanda,twelvedata,yahoo")
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.setattr(mp, "_fetch_oanda", lambda *args: (_ for _ in ()).throw(RuntimeError("not configured")))
    monkeypatch.setattr(mp, "_fetch_twelvedata", lambda *args: (_ for _ in ()).throw(RuntimeError("not configured")))
    expected = {"timestamp": [1], "indicators": {"quote": [{"close": [1.1]}]}}
    monkeypatch.setattr(mp, "_fetch_yahoo", lambda *args: expected)
    assert mp.fetch_chart_result("EURUSD", "1m") == expected
    assert mp.LAST_PROVIDER_BY_SYMBOL["EURUSD"] == "yahoo"


def test_oanda_requires_token_without_disclosing_it(monkeypatch):
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    try:
        mp._fetch_oanda("EURUSD", "1min")
    except RuntimeError as exc:
        assert str(exc) == "OANDA_NOT_CONFIGURED_FOR_SYMBOL"
    else:
        raise AssertionError("OANDA should not run without credentials")
