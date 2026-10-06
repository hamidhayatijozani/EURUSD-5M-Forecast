"""Resolve locked forecasts without changing the original prediction."""
from datetime import datetime, timezone

def _dt(x):
    d=datetime.fromisoformat(x.replace("Z","+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def validate_window(issued_at,target_at,resolved_at,feature_cutoff_at):
    i,t,r,f=map(_dt,(issued_at,target_at,resolved_at,feature_cutoff_at))
    if not (f<=i<t<=r): raise ValueError("INVALID temporal ordering")
    return True

def resolve(prediction,actual,baseline_prediction,resolved_at,friction=(0.00002,0.0,0.0)):
    validate_window(prediction["issued_at"],prediction["target_at"],resolved_at,prediction["feature_cutoff_at"])
    spread,slippage,commission=map(float,friction)
    p=float(prediction["prediction"]); b=float(baseline_prediction); a=float(actual)
    direction=1 if p>0 else -1 if p<0 else 0
    gross=direction*a
    net=gross-spread-slippage-commission
    return dict(prediction, resolved_at=resolved_at, actual=a, baseline_prediction=b,
        error_absolute=abs(a-p),baseline_error_absolute=abs(a-b),
        direction_hit=bool(direction and direction*a>spread+slippage+commission),
        gross_return=gross,spread_cost=spread,slippage_cost=slippage,
        commission_cost=commission,friction_adjusted_return=net,status="VALID")
