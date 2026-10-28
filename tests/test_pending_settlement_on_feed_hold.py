from datetime import datetime, timedelta, timezone

from scripts import live_minute_loop as loop


def test_cycle_settles_due_rows_before_holding_for_gapped_feature_feed(monkeypatch):
    events = []
    feed_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=5)
    state = {
        "last_prediction": "2026-10-12T12:00:00+00:00",
        "resolved": 0,
        "correct": 0,
        "errors": [],
    }
    predictions = [{"prediction_id": "pending-1", "status": "PENDING"}]
    fetch_calls = []

    monkeypatch.setattr(loop, "load_state", lambda: state)
    monkeypatch.setattr(loop, "read_predictions", lambda: predictions)

    # The current cycle uses one primary OHLC snapshot for both settlement and
    # feature construction. Keep the fake compatible with that production API.
    def fake_fetch_ohlc(symbol="EURUSD"):
        fetch_calls.append(symbol)
        return [(feed_ts, 1.0, 1.2, 0.9, 1.1)]

    monkeypatch.setattr(loop.live_feed_adapter, "fetch_1m_ohlc", fake_fetch_ohlc)

    def fake_settle(rows, times, prices, current_state, code_commit):
        events.append("settle")
        rows[0]["status"] = "RESOLVED"
        return True

    monkeypatch.setattr(loop, "settle", fake_settle)
    monkeypatch.setattr(loop, "save_predictions", lambda rows: events.append("save_predictions"))
    monkeypatch.setattr(loop, "save_state", lambda current_state: events.append("save_state"))
    monkeypatch.setattr(loop, "git_commit", lambda: events.append("git_commit"))

    def broken_feature_feed(when=None, *, primary_ohlc_rows=None):
        events.append("feature_feed")
        raise RuntimeError("INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES:1")

    monkeypatch.setattr(loop, "aligned_closed_1m_series", broken_feature_feed)

    outcome = loop.cycle()

    assert outcome == "HOLD"
    assert fetch_calls == ["EURUSD"], "cycle must fetch exactly one primary OHLC snapshot"
    assert events.index("settle") < events.index("feature_feed")
    assert predictions[0]["status"] == "RESOLVED"
