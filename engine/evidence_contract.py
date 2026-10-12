"""Strict temporal contract for forecast evidence records."""
from datetime import datetime, timezone


class TemporalContractError(ValueError):
    """Evidence timestamps violate the forecast information boundary."""


def _dt(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise TemporalContractError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None:
        raise TemporalContractError("TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def validate_temporal_contract(record):
    """Require feature_cutoff_at < issued_at < target_ts, strictly."""
    try:
        cutoff = _dt(record["feature_cutoff_at"])
        issued = _dt(record["issued_at"])
        target = _dt(record["target_ts"])
    except KeyError as exc:
        raise TemporalContractError(f"MISSING_TIMESTAMP:{exc.args[0]}") from exc
    if not cutoff < issued < target:
        raise TemporalContractError("TEMPORAL_ORDER_REQUIRED:feature_cutoff_at < issued_at < target_ts")
    return True


def build_record(*, feature_cutoff_at, issued_at, target_ts, **fields):
    record = dict(fields)
    record.update({
        "feature_cutoff_at": feature_cutoff_at,
        "issued_at": issued_at,
        "target_ts": target_ts,
    })
    validate_temporal_contract(record)
    return record
