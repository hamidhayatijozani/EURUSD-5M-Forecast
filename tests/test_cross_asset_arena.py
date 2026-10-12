from datetime import datetime, timedelta, timezone
from scripts.claimlab_cross_asset_arena import _asof, build_cross_asset_observations


def _bars(start, n, price=1.1):
    rows=[]
    for i in range(n):
        p=price*(1+0.0001*i)
        rows.append({"timestamp":start+timedelta(minutes=5*i),"open":p,
                     "high":p+0.0002,"low":p-0.0002,"close":p})
    return rows


def test_asof_never_selects_auxiliary_future_bar():
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    master=_bars(start,3)
    aux=[{"timestamp":start-timedelta(minutes=5),"close":1.2},
         {"timestamp":start+timedelta(minutes=5),"close":9.9}]
    aligned=_asof(master,aux)
    assert aligned[0]["close"]==1.2
    assert aligned[1]["close"]==9.9


def test_cross_asset_arena_skips_missing_auxiliary_history():
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    eur=_bars(start,40)
    gbp=_bars(start,40,1.3)
    jpy=_bars(start,40,150.0)
    dxy=[]  # no DXY data must not be fabricated
    rows=build_cross_asset_observations({"EURUSD":eur,"GBPUSD":gbp,"USDJPY":jpy,"DXY":dxy})
    assert rows==[]


def test_cross_asset_signal_is_invariant_to_future_target_price():
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    series={}
    for symbol,price in (("EURUSD",1.1),("GBPUSD",1.3),("USDJPY",150.0),("DXY",100.0)):
        series[symbol]=_bars(start,40,price)
    first=build_cross_asset_observations(series)
    changed={symbol:[dict(row) for row in rows] for symbol,rows in series.items()}
    changed["EURUSD"][-1]["close"]*=1.02
    changed["EURUSD"][-1]["high"]*=1.02
    second=build_cross_asset_observations(changed)
    assert first[-1]["positions"]==second[-1]["positions"]
    assert first[-1]["actual"]!=second[-1]["actual"]
