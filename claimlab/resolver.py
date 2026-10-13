"""Resolve a locked forecast exactly at its target, never by a later market price."""
from datetime import datetime, timezone


def _dt(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_window(issued_at, target_at, resolved_at, feature_cutoff_at):
    cutoff, issued, target, resolved = map(
        _dt, (feature_cutoff_at, issued_at, target_at, resolved_at)
    )
    if not (cutoff < issued < target <= resolved):
        raise ValueError("INVALID temporal ordering")
    return True


def resolve(prediction, actual, baseline_prediction, resolved_at,
            friction=(0.00002, 0.0, 0.0)):
    validate_window(
        prediction["issued_at"], prediction["target_at"], resolved_at,
        prediction["feature_cutoff_at"],
    )
    target = _dt(prediction["target_at"])
    issued = _dt(prediction["issued_at"])
    if int(prediction["horizon_seconds"]) != int((target - issued).total_seconds()):
        raise ValueError("INVALID horizon")
    spread, slippage, commission = map(float, friction)
    if min(spread, slippage, commission) < 0:
        raise ValueError("negative friction")
    predicted = float(prediction["prediction"])
    baseline = float(baseline_prediction)
    observed = float(actual)
    direction = 1 if predicted > 0 else -1 if predicted < 0 else 0
    gross = direction * observed
    net = gross - spread - slippage - commission
    directional_hit = (
        (direction == 1 and observed > spread + slippage + commission)
        or (direction == -1 and observed < -(spread + slippage + commission))
    )
    return dict(
        prediction, resolved_at=resolved_at, actual=observed,
        baseline_prediction=baseline, error_absolute=abs(observed - predicted),
        baseline_error_absolute=abs(observed - baseline),
        direction_hit=bool(directional_hit), gross_return=gross,
        spread_cost=spread, slippage_cost=slippage, commission_cost=commission,
        friction_adjusted_return=net, status="VALID",
    )
