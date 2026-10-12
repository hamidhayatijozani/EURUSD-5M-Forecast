from datetime import datetime, timedelta, timezone
from scripts.claimlab_candidate_arena import build_observations

def _rows(n=40, future_multiplier=1.0):
    rows=[]; base=datetime(2026,1,1,tzinfo=timezone.utc); price=1.1
    for i in range(n):
        opening=price
        price=price*(1.0001 if i%2==0 else 0.99995)
        if i==n-1: price*=future_multiplier
        rows.append({"timestamp":base+timedelta(minutes=5*i),"open":opening,
                     "high":max(opening,price)+0.0001,"low":min(opening,price)-0.0001,
                     "close":price,"volume":1.0})
    return rows

def test_candidate_signals_do_not_depend_on_next_bar_close():
    first=build_observations(_rows(40,1.0))
    changed=build_observations(_rows(40,1.01))
    assert first[-1]["positions"]==changed[-1]["positions"]
    assert first[-1]["actual"]!=changed[-1]["actual"]

def test_candidate_arena_skips_timestamp_gaps():
    rows=_rows(40); rows[25]["timestamp"]+=timedelta(minutes=5)
    observations=build_observations(rows)
    assert len(observations)<40-24-1
