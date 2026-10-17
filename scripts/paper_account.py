"""Deterministic, no-broker forward paper-account evaluator.

It consumes only resolved live predictions that satisfy the current timestamp
contract. It never fetches data, places orders, or tunes strategy parameters.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

PREDICTIONS = Path("research/live_predictions.jsonl")
TRADE_LEDGER = Path("research/paper_account/trades.jsonl")
SUMMARY = Path("research/paper_account/summary.json")
INITIAL_EQUITY = 10_000.0
POSITION_FRACTION = 0.20  # at most 5 overlapping one-minute signals ~= 1x exposure
SIGNAL_THRESHOLD = 0.00002
COST_SCENARIOS = (0.00002, 0.00005, 0.00010)
CONTRACT_VERSION = "freshness-90s-v2"
MAX_DRAWDOWN = 0.10


def _dt(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("missing timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid prediction JSON at line {line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"prediction line {line_number} is not an object")
        rows.append(row)
    return rows


def _eligible(row: dict) -> tuple[bool, str]:
    if row.get("data_contract_version") != CONTRACT_VERSION:
        return False, "wrong_or_missing_contract"
    if row.get("status") != "RESOLVED" or row.get("resolved_at") is None:
        return False, "unresolved"
    if row.get("freshness_status") != "FRESH":
        return False, "not_fresh"
    try:
        age = float(row["data_age_seconds"])
        limit = float(row.get("freshness_limit_seconds", 90.0))
        cutoff = _dt(row.get("feature_cutoff_at") or row.get("decision_evidence", {}).get("feature_cutoff_at"))
        issued = _dt(row["prediction_ts"])
        target = _dt(row["target_at"])
        resolved = _dt(row["resolved_at"])
        _ = float(row["predicted_return"])
        _ = float(row["actual_return"])
    except (KeyError, TypeError, ValueError, AttributeError):
        return False, "missing_or_invalid_evidence"
    if age < 0 or age > limit or limit > 90:
        return False, "stale_or_invalid_age"
    if not cutoff < issued < target <= resolved:
        return False, "temporal_contract_violation"
    if not row.get("prediction_id"):
        return False, "missing_prediction_id"
    return True, "eligible"


def _simulate(rows: list[dict], friction: float) -> dict:
    # Event simulation freezes notional at issue time. Settlements are processed
    # before new entries at the same timestamp; future outcomes never size trades.
    equity = INITIAL_EQUITY
    peak = equity
    max_drawdown = 0.0
    open_positions: dict[str, dict] = {}
    trades = []
    halted = False
    blocked_exposure = 0
    events = []
    for row in rows:
        ok, _ = _eligible(row)
        if not ok:
            continue
        predicted = float(row["predicted_return"])
        if abs(predicted) <= SIGNAL_THRESHOLD:
            continue
        events.append((_dt(row["resolved_at"]), 0, row))
        events.append((_dt(row["prediction_ts"]), 1, row))
    events.sort(key=lambda event: (event[0], event[1], event[2].get("prediction_id", "")))

    for event_time, event_kind, row in events:
        pid = row["prediction_id"]
        if event_kind == 1:  # issue: freeze size using equity known now
            if halted:
                continue
            if len(open_positions) >= 5:
                blocked_exposure += 1
                continue
            predicted = float(row["predicted_return"])
            open_positions[pid] = {
                "row": row,
                "side": 1 if predicted > 0 else -1,
                "notional_at_entry": equity * POSITION_FRACTION,
                "equity_at_entry": equity,
            }
            continue

        position = open_positions.pop(pid, None)
        if position is None:
            continue
        actual = float(row["actual_return"])
        gross_return = position["side"] * actual
        net_return = gross_return - friction
        pnl = position["notional_at_entry"] * net_return
        equity_before_settlement = equity
        equity += pnl
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 1.0
        max_drawdown = max(max_drawdown, drawdown)
        trades.append({
            "prediction_id": pid,
            "issued_at": row["prediction_ts"],
            "target_at": row["target_at"],
            "resolved_at": row["resolved_at"],
            "side": "LONG" if position["side"] > 0 else "SHORT",
            "predicted_return": float(row["predicted_return"]),
            "actual_return": actual,
            "gross_return": gross_return,
            "friction_assumption": friction,
            "net_return": net_return,
            "equity_at_entry": round(position["equity_at_entry"], 8),
            "notional_at_entry": round(position["notional_at_entry"], 8),
            "equity_before_settlement": round(equity_before_settlement, 8),
            "pnl": round(pnl, 8),
            "equity_after": round(equity, 8),
            "drawdown": round(drawdown, 8),
        })
        if drawdown >= MAX_DRAWDOWN:
            halted = True

    pnls = [float(t["pnl"]) for t in trades]
    wins = sum(x > 0 for x in pnls)
    return {
        "initial_equity": INITIAL_EQUITY,
        "final_equity": round(equity, 8),
        "net_pnl": round(equity - INITIAL_EQUITY, 8),
        "net_return_fraction": round(equity / INITIAL_EQUITY - 1.0, 8),
        "trade_count": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate": round(wins / len(trades), 8) if trades else None,
        "average_pnl": round(sum(pnls) / len(pnls), 8) if pnls else None,
        "max_drawdown_fraction": round(max_drawdown, 8),
        "drawdown_limit_fraction": MAX_DRAWDOWN,
        "halted_at_drawdown_limit": halted,
        "blocked_by_open_exposure_cap": blocked_exposure,
        "open_positions_unsettled_at_end": len(open_positions),
        "trades": trades,
    }


def evaluate(rows: list[dict]) -> tuple[dict, list[dict]]:
    counts: dict[str, int] = {}
    eligible = []
    for row in rows:
        ok, reason = _eligible(row)
        counts[reason] = counts.get(reason, 0) + 1
        if ok:
            eligible.append(row)
    scenarios = {str(cost): _simulate(eligible, cost) for cost in COST_SCENARIOS}
    primary = scenarios[str(COST_SCENARIOS[0])]
    summary = {
        "schema": "hamidcognition.paper_account.v1",
        "mode": "PAPER_ONLY_NO_BROKER",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy_mutated": False,
        "initial_equity": INITIAL_EQUITY,
        "position_fraction": POSITION_FRACTION,
        "signal_threshold": SIGNAL_THRESHOLD,
        "cost_scenarios_return_fraction": list(COST_SCENARIOS),
        "max_drawdown_stop": MAX_DRAWDOWN,
        "input_rows": len(rows),
        "eligibility_counts": counts,
        "eligible_resolved_predictions": len(eligible),
        "minimum_observations_for_edge_claim": 1000,
        "edge_claim_allowed": False,
        "profitability_claim_allowed": False,
        "primary_scenario": str(COST_SCENARIOS[0]),
        "scenarios": {cost: {k: v for k, v in result.items() if k != "trades"} for cost, result in scenarios.items()},
        "diagnostics": [],
    }
    if len(eligible) < 1000:
        summary["diagnostics"].append("INSUFFICIENT_SAMPLE_FOR_EDGE_CLAIM")
    if not eligible:
        summary["diagnostics"].append("NO_ELIGIBLE_FRESH_TEMPORALLY_VALID_SETTLEMENTS")
    if any(counts.get(k, 0) for k in ("temporal_contract_violation", "stale_or_invalid_age")):
        summary["diagnostics"].append("DATA_CONTRACT_FAILURES_PRESENT")
    if primary["trade_count"] and primary["net_pnl"] <= 0:
        summary["diagnostics"].append("PAPER_ACCOUNT_NOT_PROFITABLE_AT_PRIMARY_ASSUMED_COST")
    return summary, primary["trades"]


def main() -> int:
    rows = _load_rows(PREDICTIONS)
    summary, trades = evaluate(rows)
    TRADE_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    TRADE_LEDGER.write_text("".join(json.dumps(t, sort_keys=True) + "\n" for t in trades), encoding="utf-8")
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
