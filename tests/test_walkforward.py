import json
from datetime import datetime, timezone, timedelta

from claimlab.walkforward import parse_csv, walk_forward, regime_robustness


def test_parse_csv_normalizes_and_sorts():
    text = """datetime,open,high,low,close,volume
2026-01-01 00:05:00,1.1,1.2,1.0,1.15,10
2026-01-01 00:00:00,1.0,1.1,0.9,1.1,11
"""
    rows = parse_csv(text)
    assert rows[0]["timestamp"] < rows[1]["timestamp"]
    assert rows[0]["close"] == 1.1


def test_walk_forward_never_uses_target_bar_as_feature():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 1.0
    for i in range(20):
        ts = start + timedelta(minutes=5 * i)
        rows.append({
            "timestamp": ts,
            "open": close,
            "high": close + 0.001,
            "low": close - 0.001,
            "close": close,
            "volume": 1.0,
        })
        close += 0.001

    obs, cfg = walk_forward(rows, code_commit="test")
    assert obs
    first = json.loads(obs[0].canonical())
    assert first["feature_cutoff_at"] == first["issued_at"]
    assert first["issued_at"] < first["target_at"]
    assert first["horizon_seconds"] == 300
    # The target return is resolved from the target bar, not the following bar.
    expected = rows[13]["close"] / rows[12]["close"] - 1.0
    assert abs(first["actual"] - expected) < 1e-12

    # Mutating the target close must not change the forecast made at bar 12.
    changed_rows = [dict(row) for row in rows]
    changed_rows[13]["close"] *= 1.25
    changed_obs, _ = walk_forward(changed_rows, code_commit="test")
    changed_first = json.loads(changed_obs[0].canonical())
    assert changed_first["prediction"] == first["prediction"]
    assert changed_first["actual"] != first["actual"]
    assert cfg["baseline"] == "zero_return"



def test_regime_robustness_uses_past_only_volatility_groups():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 1.0
    for i in range(180):
        # Deterministic changing returns exercise multiple volatility levels.
        step = (0.0001 if i % 7 else 0.0015) * (1 if i % 2 else -1)
        next_close = close * (1.0 + step)
        ts = start + timedelta(minutes=5 * i)
        rows.append({
            "timestamp": ts,
            "open": close,
            "high": max(close, next_close) + 0.0002,
            "low": min(close, next_close) - 0.0002,
            "close": next_close,
            "volume": 1.0,
        })
        close = next_close

    observations, config = walk_forward(rows, code_commit="test")
    materialized = [json.loads(o.canonical()) for o in observations]
    result = regime_robustness(rows, materialized, lookback=config["lookback_bars"], bootstrap_resamples=100)
    assert result["threshold_lookback_max"] == 500
    assert result["warmup_observations_excluded"] >= 50
    assert set(result["metrics"]) == {"LOW", "MEDIUM", "HIGH"}
    grouped_n = sum(group["n"] for group in result["metrics"].values())
    assert grouped_n + result["warmup_observations_excluded"] == len(observations)
