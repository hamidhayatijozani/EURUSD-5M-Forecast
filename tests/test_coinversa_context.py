from datetime import datetime, timezone

from engine import coinversa_context as cc


def test_no_key_is_optional_and_does_not_make_network_request(monkeypatch):
    monkeypatch.delenv("COINVERSAA_API_KEY", raising=False)
    monkeypatch.setattr(cc, "_fetch_json", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call")))
    result = cc.fetch_coinversa_context(now=datetime(2026, 10, 15, tzinfo=timezone.utc))
    assert result["status"] == "UNAVAILABLE:NO_API_KEY"
    assert result["pulse_status"] == "UNAVAILABLE:NO_API_KEY"
    assert result["risk_status"] == "UNAVAILABLE:NO_API_KEY"
    assert result["eurusd_ohlc"] is False
    assert result["directional_signal"] is False


def test_pulse_and_risk_are_supplemental_and_separate(monkeypatch):
    monkeypatch.setenv("COINVERSAA_API_KEY", "test-key")
    calls = []

    def fake_fetch(url, key, timeout=5):
        calls.append((url, key))
        if url.endswith("/pulse/stats"):
            return {"total_traders": 12, "api_key": "must-not-escape"}
        return {"risk_level": "elevated", "total_liquidations": 3}

    monkeypatch.setattr(cc, "_fetch_json", fake_fetch)
    result = cc.fetch_coinversa_context()
    assert result["status"] == "OK"
    assert result["pulse_status"] == "OK"
    assert result["risk_status"] == "OK"
    assert result["pulse"]["total_traders"] == 12
    assert "api_key" not in result["pulse"]
    assert result["risk"]["risk_level"] == "elevated"
    assert result["eurusd_ohlc"] is False
    assert result["directional_signal"] is False
    assert len(calls) == 2
    assert all(key == "test-key" for _, key in calls)


def test_provider_failure_is_nonfatal_and_does_not_leak_error(monkeypatch):
    monkeypatch.setenv("COINVERSAA_API_KEY", "secret-key")

    def fake_fetch(url, key, timeout=5):
        if url.endswith("/pulse/stats"):
            raise RuntimeError("request failed with secret-key")
        return {"risk": 1}

    monkeypatch.setattr(cc, "_fetch_json", fake_fetch)
    result = cc.fetch_coinversa_context()
    assert result["status"] == "OK"
    assert result["pulse_status"] == "UNAVAILABLE:RuntimeError"
    assert result["risk_status"] == "OK"
    assert "secret-key" not in str(result)


def test_all_provider_failures_are_reported_as_unavailable(monkeypatch):
    monkeypatch.setenv("COINVERSAA_API_KEY", "test-key")
    monkeypatch.setattr(cc, "_fetch_json", lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError()))
    result = cc.fetch_coinversa_context()
    assert result["status"] == "UNAVAILABLE"
    assert result["pulse_status"] == "UNAVAILABLE:TimeoutError"
    assert result["risk_status"] == "UNAVAILABLE:TimeoutError"


def test_payload_is_bounded_and_redacts_secret_like_keys():
    result = cc._safe_payload({
        "safe": "x" * 300,
        "nested": {"authorization": "bearer-secret", "value": 1},
        "api_key": "do-not-return",
    })
    assert len(result["safe"]) == 256
    assert "api_key" not in result
    assert "authorization" not in result["nested"]
    assert result["nested"]["value"] == 1
