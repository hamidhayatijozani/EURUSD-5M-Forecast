"""Immutable ClaimLab observation contract with hard temporal and numeric invariants."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib, json, math

def _dt(value):
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

@dataclass(frozen=True)
class Observation:
    schema_version:str
    prediction_id:str
    issued_at:str
    target_at:str
    resolved_at:str
    symbol:str
    horizon_seconds:int
    prediction:float
    actual:float
    baseline_prediction:float
    error_absolute:float
    baseline_error_absolute:float
    direction_hit:bool
    gross_return:float
    spread_cost:float
    slippage_cost:float
    commission_cost:float
    friction_adjusted_return:float
    feature_cutoff_at:str
    code_commit:str
    config_hash:str
    claim_registry_hash:str
    status:str="VALID"

    def __post_init__(self):
        if self.status not in {"VALID","INVALID"}:
            raise ValueError("INVALID observation status")
        if not self.prediction_id or not self.symbol:
            raise ValueError("missing immutable identity")
        f,i,t,r=map(_dt,(self.feature_cutoff_at,self.issued_at,self.target_at,self.resolved_at))
        if not (f <= i < t <= r):
            raise ValueError("INVALID temporal ordering")
        horizon=(t-i).total_seconds()
        if int(self.horizon_seconds) != int(horizon):
            raise ValueError("horizon_seconds mismatch")
        for name in (
            "prediction","actual","baseline_prediction","error_absolute",
            "baseline_error_absolute","gross_return","spread_cost",
            "slippage_cost","commission_cost","friction_adjusted_return",
        ):
            if not math.isfinite(float(getattr(self,name))):
                raise ValueError(f"non-finite {name}")
        if min(self.spread_cost,self.slippage_cost,self.commission_cost) < 0:
            raise ValueError("negative transaction cost")

    def canonical(self):
        return json.dumps(asdict(self),sort_keys=True,separators=(",",":"))

    def digest(self):
        return hashlib.sha256(self.canonical().encode()).hexdigest()
