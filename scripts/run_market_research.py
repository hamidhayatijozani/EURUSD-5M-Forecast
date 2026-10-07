"""Run rolling real-market experiments with explicit partial-feed semantics."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.experiments import baseline, pst_signal, cross_asset_signal, combined, resolve, summarize
from engine.live_feed import aligned_closed_series, closed_rows


def _write(payload):
    Path("research/results").mkdir(parents=True, exist_ok=True)
    Path("research/results/latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def _latest_contiguous(rows):
    rows = sorted(rows, key=lambda row: row[0])
    if not rows:
        return []
    start = len(rows) - 1
    while start > 0 and rows[start][0] - rows[start - 1][0] == timedelta(minutes=5):
        start -= 1
    return rows[start:]


def run(data_loader=aligned_closed_series, eurusd_loader=closed_rows):
    generated_at = datetime.now(timezone.utc).isoformat()
    partial = False
    primary_error = None
    try:
        data, times = data_loader()
        if len(times) < 14:
            raise RuntimeError(f"INSUFFICIENT_COMMON_CLOSED_CANDLES:{len(times)}")
    except Exception as exc:
        primary_error = f"{type(exc).__name__}: {exc}"
        # EURUSD-only metrics remain valid for baseline/PST. Do not fabricate
        # cross-asset inputs or pretend the unavailable strategies were tested.
        try:
            rows = _latest_contiguous(eurusd_loader("EURUSD"))
            if len(rows) < 14:
                raise RuntimeError(f"INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES:{len(rows)}")
            times = [row[0] for row in rows]
            data = {"EURUSD": [float(row[1]) for row in rows]}
            partial = True
        except Exception as fallback_exc:
            payload = {
                "generated_at": generated_at,
                "instrument": "EURUSD",
                "timeframe": "5m",
                "data_source": "Yahoo Finance research adapter",
                "research_status": "DATA_UNAVAILABLE",
                "metrics_computed": False,
                "reason": f"primary={primary_error}; EURUSD_fallback={type(fallback_exc).__name__}: {fallback_exc}",
                "scientific_boundary": "No market metrics or performance claim computed.",
            }
            _write(payload)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return payload

    results = {}
    strategy_names = ("BASELINE", "EXP-006", "EXP-007", "COMBINATION")
    for name in strategy_names:
        if partial and name in ("EXP-007", "COMBINATION"):
            results[name] = {
                "n": 0,
                "status": "DATA_UNAVAILABLE",
                "reason": "Fresh, time-aligned auxiliary cross-asset candles unavailable.",
            }
            continue
        returns = []
        for i in range(12, len(times) - 1):
            # The target must be the next 5-minute candle, not merely the next
            # available quote after a gap.
            if times[i + 1] - times[i] != timedelta(minutes=5):
                continue
            window = {k: v[i - 12:i] for k, v in data.items()}
            if name == "BASELINE":
                signal = baseline(window["EURUSD"])
            elif name == "EXP-006":
                signal = pst_signal(window["EURUSD"])
            elif name == "EXP-007":
                signal = cross_asset_signal(window)
            else:
                signal = combined(window)
            returns.append(resolve(signal, data["EURUSD"][i], data["EURUSD"][i + 1]))
        results[name] = summarize(returns)

    available = {k: v for k, v in results.items() if "avg_return" in v and v.get("n", 0)}
    payload = {
        "generated_at": generated_at,
        "instrument": "EURUSD",
        "timeframe": "5m",
        "windows": len(times) - 13,
        "data_source": "Yahoo Finance research adapter" + ("; EURUSD-only fallback" if partial else ""),
        "strategies": results,
        "best_by_average_return": max(available, key=lambda k: available[k]["avg_return"]) if available else None,
        "research_status": "PARTIAL_DATA" if partial else "observed_market_data_not_a_profitability_claim",
        "metrics_computed": bool(available),
        "auxiliary_cross_asset_status": "DATA_UNAVAILABLE" if partial else "ALIGNED",
        "fallback_reason": primary_error if partial else None,
        "scientific_boundary": (
            "EURUSD-only metrics are descriptive research; unavailable cross-asset strategies were not scored."
            if partial else
            "Observed market data only; no profitability claim."
        ),
    }
    _write(payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    run()
