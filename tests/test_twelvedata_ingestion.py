from datetime import datetime, timedelta, timezone

import pytest

from claimlab.twelvedata import TwelveDataError, TwelveDataEURUSD5mClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return FakeResponse(self.payload)


def row(timestamp, open_="1.1000", high="1.1010", low="1.0990", close="1.1005"):
    return {"datetime": timestamp, "open": open_, "high": high, "low": low, "close": close}


def test_requires_api_key():
    with pytest.raises(TwelveDataError, match="TWELVEDATA_API_KEY"):
        TwelveDataEURUSD5mClient(api_key="")


def test_requests_eurusd_five_minute_data_and_returns_completed_candle():
    now = datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc)
    session = FakeSession({"meta": {"symbol": "EUR/USD"}, "values": [
        row("2026-10-13 06:20:00"),  # still forming at 06:22, must be excluded
        row("2026-10-13 06:15:00", close="1.1004"),
        row("2026-10-13 06:10:00", close="1.1003"),
    ]})
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=session)
    result = client.fetch_latest_eurusd_candle(now=now)
    assert result["provider"] == "twelve_data"
    assert result["symbol"] == "EURUSD"
    assert result["interval"] == "5min"
    assert result["timestamp"] == "2026-10-13T06:15:00+00:00"
    assert result["candle_closed_at"] == "2026-10-13T06:20:00+00:00"
    assert result["freshness_status"] == "FRESH"
    assert result["close"] == 1.1004
    assert len(result["raw_payload_hash"]) == 64
    args, kwargs = session.calls[0]
    assert args[0] == TwelveDataEURUSD5mClient.ENDPOINT
    assert kwargs["params"]["symbol"] == "EUR/USD"
    assert kwargs["params"]["interval"] == "5min"
    assert kwargs["params"]["timezone"] == "UTC"
    assert kwargs["timeout"] == 12.0


def test_rejects_provider_error_without_echoing_provider_message():
    session = FakeSession({"status": "error", "code": 401, "message": "secret query key invalid"})
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=session)
    with pytest.raises(TwelveDataError, match="rejected") as exc:
        client.fetch_latest_eurusd_candle(now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc))
    assert "secret" not in str(exc.value)


def test_rejects_missing_values():
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=FakeSession({"values": []}))
    with pytest.raises(TwelveDataError, match="No EUR/USD"):
        client.fetch_latest_eurusd_candle(now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc))


def test_rejects_invalid_ohlc():
    session = FakeSession({"values": [row("2026-10-13 06:15:00", high="1.0995", low="1.1000")]})
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=session)
    with pytest.raises(TwelveDataError, match="Invalid EUR/USD OHLC"):
        client.fetch_latest_eurusd_candle(now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc))


def test_stale_candle_is_marked_stale_not_mislabeled_live():
    session = FakeSession({"values": [row("2026-10-13 05:00:00")]})
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=session, max_age_seconds=300)
    result = client.fetch_latest_eurusd_candle(now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc))
    assert result["freshness_status"] == "STALE"
    assert result["data_age_seconds"] > 300


def test_no_completed_candle_is_explicit_failure():
    session = FakeSession({"values": [row("2026-10-13 06:20:00")]})
    client = TwelveDataEURUSD5mClient("not-a-real-key", session=session)
    with pytest.raises(TwelveDataError, match="No completed"):
        client.fetch_latest_eurusd_candle(now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc))

def test_reads_repository_secret_name_from_environment(monkeypatch):
    monkeypatch.setenv("TWELVEDATA_API_KEY", "canonical-test-key")
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    client = TwelveDataEURUSD5mClient(
        session=FakeSession({"values": [row("2026-10-13 06:15:00")]})
    )
    result = client.fetch_latest_eurusd_candle(
        now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc)
    )
    assert result["freshness_status"] == "FRESH"
    _, kwargs = client.session.calls[0]
    assert kwargs["params"]["apikey"] == "canonical-test-key"


def test_legacy_api_key_environment_alias_remains_supported(monkeypatch):
    monkeypatch.delenv("TWELVEDATA_API_KEY", raising=False)
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "legacy-test-key")
    client = TwelveDataEURUSD5mClient(
        session=FakeSession({"values": [row("2026-10-13 06:15:00")]})
    )
    client.fetch_latest_eurusd_candle(
        now=datetime(2026, 10, 13, 6, 22, tzinfo=timezone.utc)
    )
    _, kwargs = client.session.calls[0]
    assert kwargs["params"]["apikey"] == "legacy-test-key"

