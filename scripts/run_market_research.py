"""Run rolling real-market 5m experiments without disguising feed outages as results."""
import json
from datetime import datetime, timezone
from pathlib import Path

from engine.experiments import baseline, pst_signal, cross_asset_signal, combined, resolve, summarize
from engine.live_feed import aligned_closed_series


def _write(payload):
    Path("research/results").mkdir(parents=True, exist_ok=True)
    Path("research/results/latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def run(data_loader=aligned_closed_series):
    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        data, times = data_loader()
        if len(times) < 14:
            raise RuntimeError(f"INSUFFICIENT_COMMON_CLOSED_CANDLES:{len(times)}")
    except Exception as exc:
        # External quotes are an optional research input. Record the outage
        # explicitly and let the independent historical walk-forward continue.
        payload = {
            "generated_at": generated_at,
            "instrument": "EURUSD",
            "timeframe": "5m",
            "data_source": "Yahoo Finance research adapter",
            "research_status": "DATA_UNAVAILABLE",
            "metrics_computed": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "scientific_boundary": "No market metrics or performance claim computed.",
        }
        _write(payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return payload

    results = {}
    for name in ("BASELINE", "EXP-006", "EXP-007", "COMBINATION"):
        returns = []
        for i in range(12, len(times) - 1):
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
    best = max(results, key=lambda k: results[k]["avg_return"])
    payload = {
        "generated_at": generated_at,
        "instrument": "EURUSD",
        "timeframe": "5m",
        "windows": len(times) - 13,
        "data_source": "Yahoo Finance research adapter",
        "strategies": results,
        "best_by_average_return": best,
        "research_status": "observed_market_data_not_a_profitability_claim",
        "metrics_computed": True,
    }
    _write(payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


if __name__ == "__main__":
    run()
