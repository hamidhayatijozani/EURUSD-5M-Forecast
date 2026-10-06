"""Immutable ClaimLab observation contract."""
from dataclasses import dataclass, asdict
import hashlib, json

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

    def canonical(self):
        return json.dumps(asdict(self),sort_keys=True,separators=(",",":"))

    def digest(self):
        return hashlib.sha256(self.canonical().encode()).hexdigest()
