from datetime import datetime, timezone
from engine.live_feed import latest_complete_window

def test_latest_window_filters_future_rows(monkeypatch):
    import engine.live_feed as lf
    now=datetime(2026,10,4,18,0,tzinfo=timezone.utc)
    rows=[(datetime(2026,10,4,17,0+i,tzinfo=timezone.utc),1.1+i/10000) for i in range(12)]
    rows.append((datetime(2026,10,4,18,1,tzinfo=timezone.utc),9.9))
    monkeypatch.setattr(lf,"fetch_5m_closes",lambda symbol:rows)
    result=latest_complete_window(now)
    assert len(result)==12
    assert 9.9 not in result


def test_asof_alignment_uses_only_prior_quotes(monkeypatch):
    import engine.live_feed as lf
    from datetime import timedelta

    t0 = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    master = [(t0 + timedelta(minutes=5 * i), 1.1 + i) for i in range(4)]
    series = {
        "EURUSD": master,
        "GBPUSD": [
            (t0 - timedelta(minutes=1), 1.2),
            (t0 + timedelta(minutes=9), 99.0),  # future relative to master[1]
            (t0 + timedelta(minutes=14), 1.3),
        ],
    }
    aligned, times = lf._align_asof(
        master, series, max_age=timedelta(minutes=10), limit=10
    )
    assert times[0] == t0
    assert aligned["GBPUSD"][0][1] == 1.2
    # At t0+5m, the quote at t0+9m is future data and cannot be selected.
    assert aligned["GBPUSD"][1][1] == 1.2
