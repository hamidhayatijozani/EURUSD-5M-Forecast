from datetime import datetime, timedelta, timezone

from engine import market_providers as mp
from engine.live_feed import BASE_1M, _fetch


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



def _minute_ohlc_series(last_open, count=36, price=1.1):
    opens = [last_open - timedelta(minutes=count - index - 1) for index in range(count)]
    timestamps = [int(value.timestamp()) for value in opens]
    values = [price] * count
    return {
        "timestamp": timestamps,
        "indicators": {
            "quote": [{
                "open": values,
                "high": values,
                "low": values,
                "close": values,
            }]
        },
    }


def _unconfigured_provider(*_args):
    raise RuntimeError("not configured")


def test_live_minute_failover_skips_future_only_twelvedata_candles(monkeypatch):
    now_floor = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    future = _minute_ohlc_series(now_floor + timedelta(hours=3, minutes=35))
    fresh = _minute_ohlc_series(now_floor - timedelta(minutes=1), price=1.12)
    monkeypatch.setenv("LIVE_FEED_PROVIDERS", "oanda,twelvedata,yahoo")
    monkeypatch.setattr(mp, "_fetch_oanda", _unconfigured_provider)
    monkeypatch.setattr(mp, "_fetch_twelvedata", lambda *_args: future)
    monkeypatch.setattr(mp, "_fetch_yahoo", lambda *_args: fresh)
    mp.LAST_PROVIDER_BY_SYMBOL.clear()

    result = _fetch("EURUSD", BASE_1M)

    assert result == fresh
    assert mp.LAST_PROVIDER_BY_SYMBOL["EURUSD"] == "yahoo"


def test_live_minute_failover_skips_stale_twelvedata_candles(monkeypatch):
    now_floor = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    stale = _minute_ohlc_series(now_floor - timedelta(minutes=31))
    fresh = _minute_ohlc_series(now_floor - timedelta(minutes=1), price=1.12)
    monkeypatch.setenv("LIVE_FEED_PROVIDERS", "oanda,twelvedata,yahoo")
    monkeypatch.setattr(mp, "_fetch_oanda", _unconfigured_provider)
    monkeypatch.setattr(mp, "_fetch_twelvedata", lambda *_args: stale)
    monkeypatch.setattr(mp, "_fetch_yahoo", lambda *_args: fresh)
    mp.LAST_PROVIDER_BY_SYMBOL.clear()

    result = _fetch("EURUSD", BASE_1M)

    assert result == fresh
    assert mp.LAST_PROVIDER_BY_SYMBOL["EURUSD"] == "yahoo"

def test_safe_failure_codes_are_actionable_without_leaking_provider_details():
    assert mp._safe_failure_code(ValueError("stale one-minute OHLC candles")) == "STALE_CANDLES"
    assert mp._safe_failure_code(ValueError("Twelve Data returned provider error")) == "PROVIDER_REJECTED"
    assert mp._safe_failure_code(RuntimeError("OANDA_NOT_CONFIGURED_FOR_SYMBOL")) == "NOT_CONFIGURED"

    error = HTTPError(
        "https://api.twelvedata.com/time_series?apikey=do-not-log",
        429,
        "Too Many Requests",
        {},
        None,
    )
    assert mp._safe_failure_code(error) == "HTTP_429"
    assert "do-not-log" not in mp._safe_failure_code(error)


def test_all_provider_failures_report_safe_codes_only(monkeypatch):
    monkeypatch.setenv("LIVE_FEED_PROVIDERS", "twelvedata,yahoo")

    def fail_with_secret(*_args):
        raise ValueError("apikey=do-not-log")

    def fail_rate_limited(*_args):
        raise HTTPError(
            "https://query1.finance.yahoo.com/chart?token=do-not-log",
            429,
            "Too Many Requests",
            {},
            None,
        )

    monkeypatch.setattr(mp, "_fetch_twelvedata", fail_with_secret)
    monkeypatch.setattr(mp, "_fetch_yahoo", fail_rate_limited)

    try:
        mp.fetch_chart_result("EURUSD", "1m")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("all providers failed, expected RuntimeError")

    assert message == (
        "ALL_MARKET_PROVIDERS_FAILED:"
        "twelvedata:UNCLASSIFIED_VALUE_ERROR,yahoo:HTTP_429"
    )
    assert "do-not-log" not in message


def test_live_validator_failure_is_classified_without_raw_exception_text(monkeypatch):
    monkeypatch.setenv("LIVE_FEED_PROVIDERS", "yahoo")
    expected = {"timestamp": [1], "indicators": {"quote": [{"close": [1.1]}]}}
    monkeypatch.setattr(mp, "_fetch_yahoo", lambda *args: expected)

    def stale_validator(_result):
        raise ValueError("stale one-minute OHLC candles")

    try:
        mp.fetch_chart_result("EURUSD", "1m", result_validator=stale_validator)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("stale provider result should be rejected")

    assert message == "ALL_MARKET_PROVIDERS_FAILED:yahoo:STALE_CANDLES"

