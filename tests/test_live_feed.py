from datetime import datetime, timezone
from engine.live_feed import latest_complete_window

def test_latest_window_filters_future_rows(monkeypatch):
    import engine.live_feed as lf
    now=datetime(2026,10,4,18,0,tzinfo=timezone.utc)
    rows=[(datetime(2026,10,4,17,0+i,tzinfo=timezone.utc),1.1+i/10000) for i in range(12)]
    rows.append((datetime(2026,10,4,18,1,tzinfo=timezone.utc),9.9))
    monkeypatch.setattr(lf,"fetch_5m_closes",lambda:rows)
    result=latest_complete_window(now)
    assert len(result)==12
    assert 9.9 not in result
