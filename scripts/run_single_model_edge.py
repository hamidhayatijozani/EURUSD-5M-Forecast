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
REG_PATH = ROOT / "research/EURUSD_M5_XGB_EDGE_001_FILTER80_PREREGISTRATION.json"
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
    """Metrics for a set of already-decided positions; all costs are round-trip."""
    trades = []
    daily_net = {}
    daily_counts = {}
    for s, pos in zip(samples, positions):
        if pos == 0:
            continue
        net = pos * s["actual_return"] - COST
        trades.append((net, int(net > 0)))
        day = s["target_timestamp"].date().isoformat()
        daily_counts[day] = daily_counts.get(day, 0) + 1
        daily_net[day] = daily_net.get(day, 0.0) + net
    if not trades:
        return {"trades": 0, "hit_rate": None, "hit_rate_after_cost": None,
                "net_return_sum": 0.0, "net_sharpe_after_cost": None,
                "signals_per_day": 0.0, "cost_per_day_pips": 0.0}
    nets = [x[0] for x in trades]
    daily_values = list(daily_net.values())
    avg = sum(daily_values) / len(daily_values)
    variance = sum((x - avg) ** 2 for x in daily_values) / max(len(daily_values) - 1, 1)
    sharpe = avg / math.sqrt(variance) * math.sqrt(252) if variance > 0 else None
    day_count = max(len({s["target_timestamp"].date() for s in samples}), 1)
    return {
        "trades": len(trades),
        "hit_rate": sum(1 for s, p in zip(samples, positions) if p and ((p == 1 and s["y"] == 1) or (p == -1 and s["y"] == 0))) / len(trades),
        "hit_rate_after_cost": sum(x[1] for x in trades) / len(trades),
        "net_return_sum": sum(nets),
        "net_sharpe_after_cost": sharpe,
        "signals_per_day": len(trades) / day_count,
        "cost_per_day_pips": len(trades) * 1.5 / day_count,
    }


def _bucket_metrics(samples, probs, low, high, include_high=False):
    selected = [(s, p) for s, p in zip(samples, probs)
                if p >= low and (p <= high if include_high else p < high)]
    if not selected:
        return {"count": 0, "hit_rate": None, "hit_rate_after_cost": None}
    correct = []
    profitable = []
    for s, p in selected:
        pos = 1 if p >= 0.5 else -1
        correct.append(int((pos == 1 and s["y"] == 1) or (pos == -1 and s["y"] == 0)))
        profitable.append(int(pos * s["actual_return"] - COST > 0))
    return {"count": len(selected), "hit_rate": sum(correct) / len(correct),
            "hit_rate_after_cost": sum(profitable) / len(profitable)}

def evaluate(samples):
    """Fixed expanding chronological walk-forward; only untouched test predictions are scored."""
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
            probs = model.predict_proba([s["x"] for s in test])[:, 1].tolist()
            positions = [1 if p >= .80 else -1 if p <= .20 else 0 for p in probs]
            filtered = _metrics(test, positions)
            high = _bucket_metrics(test, probs, .80, 1.0000000001, True)
            low = _bucket_metrics(test, probs, 0.0, .20, True)
            calibration = []
            edges = [(.50,.55),(.55,.60),(.60,.65),(.65,.70),(.70,.75),(.75,.80),(.80,.85),(.85,.90),(.90,1.0000000001)]
            for lo, hi in edges:
                m = _bucket_metrics(test, probs, lo, hi, True)
                calibration.append({"bucket": f"{lo:.2f}-{min(hi,1.0):.2f}", **m})
            # Pre-filter directional output is one prediction per evaluated sample.
            folds.append({
                "train_start": _utc(train[0]["timestamp"]),
                "train_end": _utc(train[-1]["timestamp"]),
                "test_start": _utc(test[0]["timestamp"]),
                "test_end": _utc(test[-1]["timestamp"]),
                "samples_total": len(test),
                "signals_total": len(test),
                "signals_filtered_80": filtered["trades"],
                "filtered_metrics": filtered,
                "hit_rate_80_bucket": high["hit_rate"],
                "hit_rate_80_after_cost": high["hit_rate_after_cost"],
                "count_80_bucket": high["count"],
                "hit_rate_20_bucket": low["hit_rate"],
                "hit_rate_20_after_cost": low["hit_rate_after_cost"],
                "count_20_bucket": low["count"],
                "calibration": calibration,
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
        "schema": "claimlab.single_model_edge_result.v2",
        "preregistration_path": "research/EURUSD_M5_XGB_EDGE_001_FILTER80_PREREGISTRATION.json",
        "preregistration_sha256": hashlib.sha256(REG_PATH.read_bytes()).hexdigest(),
        "dataset": {"url": URL, "sha256": digest, "rows": len(rows),
                    "start_utc": actual_range[0], "end_utc": actual_range[1]},
        "model": registration["model"],
        "features": FEATURES,
        "filter": "prob >= 0.80 or prob <= 0.20",
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
            total_samples = sum(f["samples_total"] for f in folds)
            filtered_count = sum(f["signals_filtered_80"] for f in folds)
            high_count = sum(f["count_80_bucket"] for f in folds)
            low_count = sum(f["count_20_bucket"] for f in folds)
            high_hits = sum((f["hit_rate_80_bucket"] or 0) * f["count_80_bucket"] for f in folds)
            high_after = sum((f["hit_rate_80_after_cost"] or 0) * f["count_80_bucket"] for f in folds)
            low_hits = sum((f["hit_rate_20_bucket"] or 0) * f["count_20_bucket"] for f in folds)
            low_after = sum((f["hit_rate_20_after_cost"] or 0) * f["count_20_bucket"] for f in folds)
            filtered_trades = sum(f["filtered_metrics"]["trades"] for f in folds)
            net_sum = sum(f["filtered_metrics"]["net_return_sum"] for f in folds)
            daily_count = len({day for f in folds for day in []})
            # Use calendar-day span of the untouched test periods, including no-trade days.
            first_test = datetime.fromisoformat(folds[0]["test_start"].replace("Z", "+00:00")).date()
            last_test = datetime.fromisoformat(folds[-1]["test_end"].replace("Z", "+00:00")).date()
            calendar_days = max((last_test - first_test).days + 1, 1)
            day_nets = {}
            for f in folds:
                fm = f["filtered_metrics"]
                # Net daily returns are not persisted individually; use summed net return and
                # fold metrics for the aggregate Sharpe proxy, labelled as fold-mean.
            sharpes = [f["filtered_metrics"]["net_sharpe_after_cost"] for f in folds if f["filtered_metrics"]["net_sharpe_after_cost"] is not None]
            calibration_rows = []
            for idx, label in enumerate(["0.50-0.55","0.55-0.60","0.60-0.65","0.65-0.70","0.70-0.75","0.75-0.80","0.80-0.85","0.85-0.90","0.90-1.00"]):
                bucket_folds = [f["calibration"][idx] for f in folds]
                n = sum(x["count"] for x in bucket_folds)
                hr = sum((x["hit_rate"] or 0) * x["count"] for x in bucket_folds) / n if n else None
                hac = sum((x["hit_rate_after_cost"] or 0) * x["count"] for x in bucket_folds) / n if n else None
                calibration_rows.append({"bucket": label, "count": n, "hit_rate": hr, "hit_rate_after_cost": hac})
            result["aggregate"] = {
                "signals_total": total_samples,
                "signals_filtered_80": filtered_count,
                "signals_per_day_after_filter": filtered_count / calendar_days,
                "hit_rate_80_bucket": high_hits / high_count if high_count else None,
                "hit_rate_80_after_cost": high_after / high_count if high_count else None,
                "count_80_bucket": high_count,
                "hit_rate_20_bucket": low_hits / low_count if low_count else None,
                "hit_rate_20_after_cost": low_after / low_count if low_count else None,
                "count_20_bucket": low_count,
                "sharpe_after_filter_fold_mean": sum(sharpes) / len(sharpes) if sharpes else None,
                "net_return_sum_after_filter": net_sum,
                "cost_per_day_after_filter": filtered_count * 1.5 / calendar_days,
                "calibration": calibration_rows,
                "test_calendar_days": calendar_days,
            }
            agg = result["aggregate"]
            if high_count < int(registration["minimum_high_confidence_up_signals"]):
                result["verdict"] = "INSUFFICIENT_DATA"
                result["reason"] = "FEWER_THAN_50_SIGNALS_IN_P_UP_GE_0_80_BUCKET"
            elif agg["hit_rate_80_after_cost"] is not None and agg["hit_rate_80_after_cost"] > .60:
                result["verdict"] = "EDGE_CONFIRMED"
            else:
                result["verdict"] = "EDGE_REJECTED"
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result.get(k) for k in ("status", "verdict", "reason", "preregistration_sha256", "dataset", "aggregate")}, indent=2))


if __name__ == "__main__":
    main()
