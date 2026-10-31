from datetime import datetime, timezone
import hashlib
import json

import pytest

from claimlab.oanda_live import OandaConfigurationError, OandaLiveClient


class FakeResponse:
    def __init__(self, payload, headers=None):
        self._payload = payload
        self.headers = headers or {}
    def raise_for_status(self):
        return None
    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def quote_payload(timestamp=None, bid="1.10000", ask="1.10020"):
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    return {"prices": [{
        "instrument": "EUR_USD",
        "time": timestamp,
        "status": "tradeable",
        "bids": [{"price": bid}],
        "asks": [{"price": ask}],
    }]}


def test_requires_credentials():
    with pytest.raises(OandaConfigurationError):
        OandaLiveClient(token="", account_id="", environment="practice")


def test_rejects_unknown_environment():
    with pytest.raises(OandaConfigurationError):
        OandaLiveClient(token="x", account_id="y", environment="other")


def test_parses_real_provider_response_and_hashes_quote():
    payload = quote_payload()
    session = FakeSession(FakeResponse(payload, {"RequestID": "test-request"}))
    client = OandaLiveClient("token", "account", "practice", session=session)
    result = client.get_latest_quote()
    assert result["provider_id"] == "oanda_v20"
    assert result["symbol"] == "EURUSD"
    assert result["bid"] == 1.1
    assert result["ask"] == 1.1002
    assert result["freshness_status"] == "PASS"
    assert len(result["raw_payload_hash"]) == 64
    assert result["request_id"] == "test-request"
    assert session.calls[0][1]["params"] == {"instruments": "EUR_USD"}


def test_rejects_crossed_market():
    session = FakeSession(FakeResponse(quote_payload(bid="1.10100", ask="1.10000")))
    client = OandaLiveClient("token", "account", "practice", session=session)
    with pytest.raises(RuntimeError, match="Invalid EUR_USD"):
        client.get_latest_quote()


def test_marks_stale_quote_as_fail():
    old = "2000-01-01T00:00:00+00:00"
    session = FakeSession(FakeResponse(quote_payload(timestamp=old)))
    client = OandaLiveClient("token", "account", "practice", session=session)
    result = client.get_latest_quote(max_age_ms=1000)
    assert result["freshness_status"] == "FAIL"


def test_missing_price_is_explicit_error():
    session = FakeSession(FakeResponse({"prices": []}))
    client = OandaLiveClient("token", "account", "practice", session=session)
    with pytest.raises(RuntimeError, match="no EUR_USD prices"):
        client.get_latest_quote()
