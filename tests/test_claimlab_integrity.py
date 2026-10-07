from datetime import datetime, timezone, timedelta
from claimlab.resolver import validate_window, resolve
from claimlab.schema import Observation
from claimlab.statistics import StatisticalEngine

def ts(t): return t.isoformat()

def test_temporal_contract_is_hard_invariant():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    assert validate_window(ts(t),ts(t+timedelta(minutes=5)),ts(t+timedelta(minutes=6)),ts(t))
    try:
        validate_window(ts(t),ts(t+timedelta(minutes=5)),ts(t+timedelta(minutes=6)),ts(t+timedelta(seconds=1)))
    except ValueError:
        pass
    else:
        raise AssertionError("future feature cutoff was accepted")

def test_resolver_preserves_target_actual_not_later_price():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    p={"schema_version":"claimlab.observation.v1","prediction_id":"p1",
       "issued_at":ts(t),"target_at":ts(t+timedelta(minutes=5)),
       "feature_cutoff_at":ts(t),"symbol":"EURUSD","horizon_seconds":300,
       "prediction":0.001}
    r=resolve(p,actual=0.0004,baseline_prediction=0.0,
              resolved_at=ts(t+timedelta(minutes=7)))
    assert r["actual"]==0.0004

def test_observation_rejects_horizon_mismatch():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    try:
        Observation("v1","p1",ts(t),ts(t+timedelta(minutes=5)),ts(t+timedelta(minutes=5)),
          "EURUSD",60,.0,.0,.0,.0,.0,False,0,0,0,0,0,ts(t),"test","cfg","reg")
    except ValueError:
        pass
    else:
        raise AssertionError("horizon mismatch accepted")

def test_null_centered_bootstrap_does_not_use_observed_mean_as_null():
    x=[0.001]*40
    s=StatisticalEngine.block_bootstrap_ci(x,5,resamples=200,seed=7)
    assert s["p_value"] < 0.05
    z=StatisticalEngine.block_bootstrap_ci([-v for v in x],5,resamples=200,seed=7)
    # A two-sided null-centered test must treat equal-magnitude effects symmetrically.
    assert z["p_value"] < 0.05
    assert abs(s["p_value"] - z["p_value"]) < 1e-12
