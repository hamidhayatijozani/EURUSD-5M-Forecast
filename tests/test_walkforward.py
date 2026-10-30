import json
from datetime import datetime, timezone, timedelta

from claimlab.walkforward import parse_csv, walk_forward, regime_robustness, cost_sensitivity
from scripts.claimlab_walkforward import persist_dataset_snapshot


def test_parse_csv_preserves_source_order_and_normalizes_utc():
    text = """datetime,open,high,low,close,volume
2026-01-01 00:00:00,1.0,1.1,0.9,1.05,11
2026-01-01 00:05:00Z,1.05,1.2,1.0,1.15,10
"""
    rows = parse_csv(text)
    assert rows[0]["timestamp"] < rows[1]["timestamp"]
    assert rows[0]["timestamp"].tzinfo == timezone.utc
    assert rows[0]["close"] == 1.05


def test_parse_csv_rejects_out_of_order_or_duplicate_timestamps():
    out_of_order = """datetime,open,high,low,close,volume
2026-01-01 00:05:00,1.1,1.2,1.0,1.15,10
2026-01-01 00:00:00,1.0,1.1,0.9,1.05,11
"""
    duplicate = """datetime,open,high,low,close,volume
2026-01-01 00:00:00,1.0,1.1,0.9,1.05,11
2026-01-01 00:00:00,1.05,1.2,1.0,1.15,10
"""
    for text in (out_of_order, duplicate):
        try:
            parse_csv(text)
        except ValueError as exc:
            assert str(exc) == "HISTORICAL_DATA_TIMESTAMP_ORDER_INVALID"
        else:
            raise AssertionError("ambiguous source timestamp order must be rejected")


def test_parse_csv_rejects_nonfinite_and_inconsistent_ohlc():
    nonfinite = """datetime,open,high,low,close,volume
2026-01-01 00:00:00,1.0,nan,0.9,1.05,11
"""
    inconsistent = """datetime,open,high,low,close,volume
2026-01-01 00:00:00,1.0,1.01,1.02,1.05,11
"""
    for text, expected in (
        (nonfinite, "HISTORICAL_DATA_NONFINITE_VALUE"),
        (inconsistent, "HISTORICAL_DATA_OHLC_INCONSISTENT"),
    ):
        try:
            parse_csv(text)
        except ValueError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError("invalid market row must be rejected")


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
    assert first["feature_cutoff_at"] < first["issued_at"]
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



def test_dataset_snapshot_preserves_exact_source_bytes_and_hash(tmp_path):
    import hashlib

    source_text = "datetime,open,high,low,close,volume\r\n2026-01-01 00:00:00,1,2,0.5,1.5,10\r\n"
    snapshot = persist_dataset_snapshot(tmp_path, source_text)
    assert snapshot.name == "dataset.csv"
    assert snapshot.read_bytes() == source_text.encode("utf-8")
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == hashlib.sha256(
        source_text.encode("utf-8")
    ).hexdigest()

def test_cost_sensitivity_separates_spread_and_slippage_components():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 1.0
    for i in range(140):
        step = 0.0002 if i % 2 else -0.0001
        next_close = close * (1.0 + step)
        ts = start + timedelta(minutes=5 * i)
        rows.append({
            "timestamp": ts,
            "open": close,
            "high": max(close, next_close) + 0.0001,
            "low": min(close, next_close) - 0.0001,
            "close": next_close,
            "volume": 1.0,
        })
        close = next_close

    observations, _ = walk_forward(rows, code_commit="test")
    materialized = [json.loads(item.canonical()) for item in observations]
    result = cost_sensitivity(materialized, bootstrap_resamples=50)

    spread_only = result["scenarios"]["spread_0.2pip_slippage_0.00pip"]
    with_slippage = result["scenarios"]["spread_0.2pip_slippage_0.10pip"]
    assert spread_only["spread_cost"] == 0.00002
    assert spread_only["slippage_cost"] == 0.0
    assert with_slippage["spread_cost"] == 0.00002
    assert with_slippage["slippage_cost"] == 0.00001
    assert with_slippage["commission_cost"] == 0.0
    assert abs(
        spread_only["metrics"]["friction_adjusted_return"]
        - with_slippage["metrics"]["friction_adjusted_return"]
        - 0.00001
    ) < 1e-12
    assert result["commission_boundary"].startswith("Commission is not priced")

