"""Run the single, frozen EUR/USD M5 gradient-boosting edge experiment."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from sklearn.ensemble import GradientBoostingClassifier

from claimlab.walkforward import parse_csv

ROOT = Path(__file__).resolve().parents[1]
REG_PATH = ROOT / "research/EURUSD_M5_XGB_EDGE_001_PREREGISTRATION.json"
OUT_PATH = ROOT / "evidence/xgb-edge-001/result.json"
URL = "https://raw.githubusercontent.com/getdata-finance/eurusd-5m-ohlcv-forex-historical-data/main/EURUSD_5m.csv"
FEATURES = [
    "return_lag_1", "return_lag_3", "return_lag_6", "return_lag_12",
    "realized_volatility_5_bars", "realized_volatility_15_bars",
    "realized_volatility_60_bars", "normalized_current_candle_range",
    "log1p_tick_volume", "utc_hour_sin",
]
COST = 1.5 * 0.0001


def _utc(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _month_add(dt, months):
    idx = dt.year * 12 + (dt.month - 1) + months
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    import calendar
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def make_samples(rows):
    """Each row uses only the current and earlier closed bars; target is next bar."""
    samples = []
    closes = [float(r["close"]) for r in rows]
    returns = [0.0] * len(rows)
    for i in range(1, len(rows)):
        returns[i] = closes[i] / closes[i - 1] - 1.0
    for i in range(60, len(rows) - 1):
        if rows[i]["timestamp"] - rows[i - 1]["timestamp"] != timedelta(minutes=5):
            continue
        if rows[i + 1]["timestamp"] - rows[i]["timestamp"] != timedelta(minutes=5):
            continue
        hist = returns[i - 59:i + 1]
        if len(hist) != 60 or not all(math.isfinite(x) for x in hist):
            continue
        bar = rows[i]
        candle_range = max(float(bar["high"]) - float(bar["low"]), 1e-12)
        x = [
            returns[i], returns[i - 2], returns[i - 5], returns[i - 11],
            math.sqrt(sum(v * v for v in returns[i - 4:i + 1])),
            math.sqrt(sum(v * v for v in returns[i - 14:i + 1])),
            math.sqrt(sum(v * v for v in hist)),
            (float(bar["high"]) - float(bar["low"])) / max(float(bar["close"]), 1e-12),
            math.log1p(max(float(bar.get("volume", 0.0)), 0.0)),
            math.sin(2 * math.pi * (bar["timestamp"].hour + bar["timestamp"].minute / 60) / 24),
        ]
        target_return = returns[i + 1]
        samples.append({
            "timestamp": bar["timestamp"],
            "target_timestamp": rows[i + 1]["timestamp"] + timedelta(minutes=5),
            "x": x,
            "y": int(target_return > 0),
            "actual_return": target_return,
            "previous_return": returns[i],
        })
    return samples


def _metrics(samples, positions):
    trades = []
    daily_net = {}
    daily = {}
    for s, pos in zip(samples, positions):
        if pos == 0:
            continue
        net = pos * s["actual_return"] - COST
        trades.append((net, int(net > 0)))
        day = s["target_timestamp"].date().isoformat()
        daily[day] = daily.get(day, 0) + 1
        daily_net[day] = daily_net.get(day, 0.0) + net
    if not trades:
        return {"trades": 0, "hit_rate_after_cost": None, "net_return_sum": 0.0,
                "net_sharpe_after_cost": None, "signals_per_day_max": max(daily.values(), default=0)}
    nets = [x[0] for x in trades]
    daily_values = list(daily_net.values())
    avg = sum(daily_values) / len(daily_values)
    variance = sum((x - avg) ** 2 for x in daily_values) / max(len(daily_values) - 1, 1)
    sharpe = (avg / math.sqrt(variance) * math.sqrt(252)) if variance > 0 else None
    return {
        "trades": len(trades),
        "hit_rate_after_cost": sum(x[1] for x in trades) / len(trades),
        "net_return_sum": sum(nets),
        "net_sharpe_after_cost": sharpe,
        "signals_per_day_max": max(daily.values(), default=0),
    }

def evaluate(samples):
    """Fixed 90-day initial train, then non-overlapping 30-day test folds."""
    first = samples[0]["timestamp"]
    train_start = first
    train_end = _month_add(first, 3)
    folds = []
    while _month_add(train_end, 1) <= samples[-1]["target_timestamp"]:
        test_end = _month_add(train_end, 1)
        train = [s for s in samples if train_start <= s["timestamp"] < train_end - timedelta(minutes=30)]
        test = [s for s in samples if train_end + timedelta(minutes=30) <= s["timestamp"] < test_end]
        if train and test:
            model = GradientBoostingClassifier(
                n_estimators=100, learning_rate=0.05, max_depth=3, random_state=20261015
            )
            model.fit([s["x"] for s in train], [s["y"] for s in train])
            probs = model.predict_proba([s["x"] for s in test])[:, 1]
            positions = [1 if p > .55 else -1 if p < .45 else 0 for p in probs]
            momentum = [1 if s["previous_return"] > 0 else -1 if s["previous_return"] < 0 else 0 for s in test]
            meanrev = [-p for p in momentum]
            always_up = [1] * len(test)
            always_down = [-1] * len(test)
            # Deterministic 50% random baseline, frozen seed.
            import random
            rng = random.Random(20261015 + len(folds))
            random_positions = [1 if rng.random() < .5 else -1 for _ in test]
            folds.append({
                "train_start": _utc(train[0]["timestamp"]),
                "train_end": _utc(train[-1]["timestamp"]),
                "test_start": _utc(test[0]["timestamp"]),
                "test_end": _utc(test[-1]["timestamp"]),
                "model": _metrics(test, positions),
                "baseline_always_up": _metrics(test, always_up),
                "baseline_always_down": _metrics(test, always_down),
                "baseline_random_50": _metrics(test, random_positions),
                "baseline_momentum": _metrics(test, momentum),
                "baseline_mean_reversion": _metrics(test, meanrev),
            })
        train_end = test_end
    return folds


def main():
    registration = json.loads(REG_PATH.read_text(encoding="utf-8"))
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    text = response.text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rows = parse_csv(text)
    actual_range = (_utc(rows[0]["timestamp"]), _utc(rows[-1]["timestamp"]))
    expected = registration["dataset"]
    expected_range = (expected["expected_start_utc"].replace("+00:00", "Z"),
                      expected["expected_end_utc"].replace("+00:00", "Z"))
    provenance_ok = digest == expected["expected_sha256"] and len(rows) == expected["expected_source_rows"] and actual_range == expected_range
    result = {
        "schema": "claimlab.single_model_edge_result.v1",
        "preregistration_path": "research/EURUSD_M5_XGB_EDGE_001_PREREGISTRATION.json",
        "preregistration_sha256": hashlib.sha256(REG_PATH.read_bytes()).hexdigest(),
        "dataset": {"url": URL, "sha256": digest, "rows": len(rows),
                    "start_utc": actual_range[0], "end_utc": actual_range[1]},
        "model": registration["model"],
        "features": FEATURES,
        "cost_pips_round_trip": 1.5,
        "status": "COMPUTED",
        "folds": [],
    }
    if not provenance_ok:
        result.update(status="INSUFFICIENT_DATA", verdict="INSUFFICIENT_DATA",
                      reason="PINNED_DATASET_PROVENANCE_MISMATCH")
    else:
        samples = make_samples(rows)
        folds = evaluate(samples)
        result["valid_samples"] = len(samples)
        result["folds"] = folds
        if len(folds) < 3:
            result.update(verdict="INSUFFICIENT_DATA", reason="FEWER_THAN_THREE_VALID_TEST_FOLDS")
        else:
            model_rows = [f["model"] for f in folds]
            hit = [m["hit_rate_after_cost"] for m in model_rows if m["hit_rate_after_cost"] is not None]
            sharpe = [m["net_sharpe_after_cost"] for m in model_rows if m["net_sharpe_after_cost"] is not None]
            signals = [m["signals_per_day_max"] for m in model_rows]
            model_net = sum(m["net_return_sum"] for m in model_rows)
            baseline_names = ["baseline_always_up", "baseline_always_down", "baseline_random_50", "baseline_momentum", "baseline_mean_reversion"]
            baseline_comparisons = {name: sum(f[name]["net_return_sum"] for f in folds) for name in baseline_names}
            all_baselines_beaten = all(model_net > v for v in baseline_comparisons.values())
            result["aggregate"] = {
                "hit_rate_after_cost": sum(m["trades"] * (m["hit_rate_after_cost"] or 0) for m in model_rows) / max(sum(m["trades"] for m in model_rows), 1),
                "net_return_sum": model_net,
                "net_sharpe_after_cost_fold_mean": sum(sharpe) / len(sharpe) if sharpe else None,
                "signals_per_day_max": max(signals, default=0),
                "baseline_net_return_sum": baseline_comparisons,
                "beats_all_baselines": all_baselines_beaten,
            }
            agg = result["aggregate"]
            success = (agg["hit_rate_after_cost"] > .53 and agg["net_return_sum"] > 0
                       and agg["net_sharpe_after_cost_fold_mean"] is not None
                       and agg["net_sharpe_after_cost_fold_mean"] > .5
                       and agg["signals_per_day_max"] <= 10 and all_baselines_beaten)
            killed = (agg["hit_rate_after_cost"] <= .51 or
                      (agg["net_sharpe_after_cost_fold_mean"] is not None and agg["net_sharpe_after_cost_fold_mean"] < .5)
                      or agg["signals_per_day_max"] > 10)
            result["verdict"] = "EDGE_CONFIRMED" if success else "EDGE_REJECTED" if killed else "INSUFFICIENT_DATA"
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result.get(k) for k in ("status", "verdict", "reason", "preregistration_sha256", "dataset", "aggregate")}, indent=2))


if __name__ == "__main__":
    main()
