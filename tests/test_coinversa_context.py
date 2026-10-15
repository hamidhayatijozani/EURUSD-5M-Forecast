import json

from engine import coinversa_context as cc


class _Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body[:size]


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("COINVERSA_CONTEXT_ENABLED", raising=False)
    monkeypatch.setenv("COINVERSAA_API_KEY", "not-a-real-key")
    result = cc.fetch_coinversa_context()
    assert result == {"source": "coinversa", "status": "DISABLED", "data": None}


def test_enabled_without_key_is_optional_unavailable(monkeypatch):
    monkeypatch.setenv("COINVERSA_CONTEXT_ENABLED", "true")
    monkeypatch.delenv("COINVERSAA_API_KEY", raising=False)
    assert cc.fetch_coinversa_context()["status"] == "UNAVAILABLE:NO_API_KEY"


def test_success_returns_opaque_context_not_fx_candles(monkeypatch):
    monkeypatch.setenv("COINVERSA_CONTEXT_ENABLED", "1")
    monkeypatch.setenv("COINVERSAA_API_KEY", "test-secret")
    payload = {"assets": {"BTC": {"net_bias": 0.2}}}
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["key"] = request.get_header("X-api-key")
        seen["timeout"] = timeout
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr(cc, "urlopen", fake_urlopen)
    result = cc.fetch_coinversa_context(timeout=1.25)
    assert result["status"] == "OK"
    assert result["source"] == "coinversa"
    assert result["data"] == payload
    assert "EURUSD" not in result["data"]
    assert seen["url"] == cc.COINVERSA_PULSE_URL
    assert seen["key"] == "test-secret"
    assert seen["timeout"] == 1.25


def test_provider_failure_does_not_raise_or_disclose_secret(monkeypatch):
    monkeypatch.setenv("COINVERSA_CONTEXT_ENABLED", "yes")
    monkeypatch.setenv("COINVERSAA_API_KEY", "super-secret")

    def fail(*args, **kwargs):
        raise RuntimeError("request failed with super-secret")

    monkeypatch.setattr(cc, "urlopen", fail)
    result = cc.fetch_coinversa_context()
    assert result == {
        "source": "coinversa",
        "status": "UNAVAILABLE:RuntimeError",
        "data": None,
    }


def test_non_object_response_is_rejected(monkeypatch):
    monkeypatch.setenv("COINVERSA_CONTEXT_ENABLED", "true")
    monkeypatch.setenv("COINVERSAA_API_KEY", "test-key")
    monkeypatch.setattr(cc, "urlopen", lambda *a, **k: _Response(b'["not", "an object"]'))
    assert cc.fetch_coinversa_context()["status"] == "UNAVAILABLE:INVALID_SCHEMA"
