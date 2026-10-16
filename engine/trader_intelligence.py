"""Evidence-gated ranking of externally supplied EUR/USD trader records.

Ported and hardened from:
https://github.com/hamidhayatijozani/EURUSD-5M-ForecastHamid/blob/main/src/trader-intelligence.js

Research-only adapter. It performs no network calls, does not discover traders, and is
not connected to the live forecast signal. Input records must come from a source the
caller is authorized to use and must preserve source provenance independently.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

TRADER_WINDOW_HOURS = 48
DEFAULT_TRADER_LIMIT = 50
_SCORE_WEIGHTS = {
    "profit_factor": 0.30,
    "win_rate": 0.25,
    "sample_size": 0.20,
    "drawdown_quality": 0.15,
    "consistency": 0.10,
}


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an explicit ISO-8601 timestamp; naive timestamps are not evidence."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _as_of(value: str | datetime) -> datetime:
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValueError("now must be a timezone-aware ISO-8601 timestamp or datetime")
    return parsed


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _closed_eurusd_trades(
    record: dict[str, Any], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    trades = record.get("trades")
    if not isinstance(trades, list):
        return []

    accepted: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        symbol = trade.get("symbol")
        if not isinstance(symbol, str) or symbol.strip().upper() != "EURUSD":
            continue
        side = str(trade.get("side", "")).strip().upper()
        if side not in {"BUY", "SELL"}:
            continue

        # The source format supports closeTimestamp; timestamp is accepted only as
        # a documented legacy alias for the close timestamp, never as issue time.
        closed_at = _parse_timestamp(trade.get("closeTimestamp") or trade.get("timestamp"))
        profit = _finite_number(trade.get("profit"))
        if closed_at is None or profit is None or not (start <= closed_at <= end):
            continue
        accepted.append({"side": side, "profit": profit, "closed_at": closed_at})
    return accepted


def _stats(trades: list[dict[str, Any]]) -> dict[str, float | int | bool | None]:
    net_profit = sum(t["profit"] for t in trades)
    gross_profit = sum(t["profit"] for t in trades if t["profit"] > 0)
    gross_loss = sum(-t["profit"] for t in trades if t["profit"] < 0)
    wins = sum(t["profit"] > 0 for t in trades)
    losses = sum(t["profit"] < 0 for t in trades)
    count = len(trades)

    # A zero loss denominator makes profit factor unbounded, not zero. Expose
    # that fact explicitly while keeping returned numeric fields JSON-safe.
    unbounded_profit_factor = gross_profit > 0 and gross_loss == 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (
        None if unbounded_profit_factor else 0.0
    )

    net_long_profit = sum(
        t["profit"] if t["side"] == "BUY" else -t["profit"] for t in trades
    )
    return {
        "trades": count,
        "net_profit": round(net_profit, 8),
        "gross_profit": round(gross_profit, 8),
        "gross_loss": round(gross_loss, 8),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / count, 6) if count else 0.0,
        "profit_factor": round(profit_factor, 6) if profit_factor is not None else None,
        "profit_factor_unbounded": unbounded_profit_factor,
        "net_long_profit": round(net_long_profit, 8),
        "average_profit": round(net_profit / count, 8) if count else 0.0,
    }


def _score(
    stats: dict[str, float | int | bool | None], record: dict[str, Any]
) -> tuple[float, dict[str, float], list[str]]:
    if stats["profit_factor_unbounded"]:
        pf_component = 1.0
    else:
        pf = float(stats["profit_factor"] or 0.0)
        pf_component = _clamp(math.log1p(max(0.0, pf)) / math.log(4.0), 0.0, 1.0)

    win_component = _clamp(float(stats["win_rate"]), 0.0, 1.0)
    sample_n = int(stats["wins"]) + int(stats["losses"])
    sample_component = _clamp(math.log1p(sample_n) / math.log(20.0), 0.0, 1.0)

    drawdown_value = _finite_number(
        record.get("maxDrawdown48h", record.get("drawdown48h"))
    )
    warnings: list[str] = []
    if drawdown_value is None:
        # Missing risk data is not treated as zero drawdown.
        drawdown_component = 0.0
        warnings.append("MISSING_48H_DRAWDOWN")
    else:
        drawdown_component = _clamp(1.0 - max(0.0, drawdown_value) / 100.0, 0.0, 1.0)

    consistency_value = _finite_number(record.get("consistency48h"))
    if consistency_value is None:
        # Missing consistency data is not treated as perfect consistency.
        consistency_component = 0.0
        warnings.append("MISSING_48H_CONSISTENCY")
    else:
        consistency_component = _clamp(consistency_value, 0.0, 1.0)

    components = {
        "profit_factor": round(pf_component, 6),
        "win_rate": round(win_component, 6),
        "sample_size": round(sample_component, 6),
        "drawdown_quality": round(drawdown_component, 6),
        "consistency": round(consistency_component, 6),
    }
    score = 100.0 * sum(_SCORE_WEIGHTS[key] * components[key] for key in _SCORE_WEIGHTS)
    return round(score, 4), components, warnings


def rank_top_traders(
    records: list[dict[str, Any]],
    now: str | datetime,
    limit: int = DEFAULT_TRADER_LIMIT,
) -> list[dict[str, Any]]:
    """Rank eligible records using only EUR/USD realized P/L in the prior 48 hours.

    Eligibility requires an ID, an explicit EURUSD symbol, BUY/SELL side, a
    timezone-aware close timestamp within the window, finite realized P/L, and
    positive net P/L over eligible trades. The window includes both endpoints.
    """
    end = _as_of(now)
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    start = end - timedelta(hours=TRADER_WINDOW_HOURS)
    ranked: list[dict[str, Any]] = []

    for record in records:
        if not isinstance(record, dict) or record.get("id") in (None, ""):
            continue
        trades = _closed_eurusd_trades(record, start, end)
        stats = _stats(trades)
        if stats["trades"] == 0 or float(stats["net_profit"]) <= 0:
            continue

        score, components, warnings = _score(stats, record)
        ranked.append({
            "id": str(record["id"]),
            "name": str(record.get("name") or record["id"]),
            "window": {
                "start": _iso_z(start),
                "end": _iso_z(end),
                **stats,
            },
            "score": score,
            "score_components": components,
            "quality_warnings": warnings,
        })

    ranked.sort(
        key=lambda item: (
            -float(item["score"]),
            -float(item["window"]["net_profit"]),
            item["id"],
        )
    )
    for position, item in enumerate(ranked[:limit], start=1):
        item["rank"] = position
    return ranked[:limit]


def consensus_from_top_traders(top_traders: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a bounded directional summary; zero coverage is explicitly unavailable."""
    if not isinstance(top_traders, list):
        raise ValueError("top_traders must be a list")

    valid: list[tuple[float, int]] = []
    for trader in top_traders:
        if not isinstance(trader, dict) or not isinstance(trader.get("window"), dict):
            continue
        score = _finite_number(trader.get("score"))
        net_long_profit = _finite_number(trader["window"].get("net_long_profit"))
        if score is None or net_long_profit is None:
            continue
        direction = 1 if net_long_profit > 0 else -1 if net_long_profit < 0 else 0
        valid.append((max(0.01, score / 100.0), direction))

    if not valid:
        return {
            "status": "UNAVAILABLE_NO_ELIGIBLE_TRADERS",
            "score": 0.0,
            "coverage": 0,
        }
    weight_sum = sum(weight for weight, _ in valid)
    score_sum = sum(weight * direction for weight, direction in valid)
    return {
        "status": "RESEARCH_ONLY",
        "score": round(_clamp(score_sum / weight_sum, -1.0, 1.0), 6),
        "coverage": len(valid),
    }
