from datetime import datetime, timezone
from scripts import live_minute_loop as loop


def test_cycle_settles_due_rows_before_holding_for_gapped_feature_feed(monkeypatch):
    events=[]
    now=datetime(2026,10,12,12,10,30,tzinfo=timezone.utc)
    state={"last_prediction":"2026-10-12T12:00:00+00:00","resolved":0,"correct":0,"errors":[]}
    predictions=[{"prediction_id":"pending-1","status":"PENDING"}]

    monkeypatch.setattr(loop, "load_state", lambda: state)
    monkeypatch.setattr(loop, "read_predictions", lambda: predictions)
    monkeypatch.setattr(loop, "closed_1m_rows", lambda symbol, when=None: [(now.replace(minute=5),1.1)])
    def fake_settle(rows,times,prices,current_state,code_commit):
        events.append("settle")
        rows[0]["status"]="RESOLVED"
        return True
    monkeypatch.setattr(loop, "settle", fake_settle)
    monkeypatch.setattr(loop, "save_predictions", lambda rows: events.append("save_predictions"))
    monkeypatch.setattr(loop, "save_state", lambda current_state: events.append("save_state"))
    monkeypatch.setattr(loop, "git_commit", lambda: events.append("git_commit"))
    def broken_feature_feed(when=None):
        events.append("feature_feed")
        raise RuntimeError("INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES:1")
    monkeypatch.setattr(loop, "aligned_closed_1m_series", broken_feature_feed)

    outcome=loop.cycle()
    assert outcome=="HOLD"
    assert events.index("settle") < events.index("feature_feed")
    assert predictions[0]["status"]=="RESOLVED"
