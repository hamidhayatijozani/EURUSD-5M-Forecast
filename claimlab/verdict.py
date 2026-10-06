"""Verdict evaluation against the canonical locked registry."""
from .registry import load_registry

def verdict(stats, registry=None):
    r=registry or load_registry()
    n=int(stats.get("n",0))
    minimum=int(r["minimum_n"])
    if n<minimum:
        return "INSUFFICIENT_DATA"
    checks=[
        float(stats.get("mae_delta",0))>0,
        float(stats.get("hit_rate",0))>=0.5,
        float(stats.get("friction_adjusted_return",0))>0,
        float(stats.get("temporal_validity_rate",1.0))==1.0,
        float(stats.get("duplicate_prediction_rate",0.0))==0.0,
        float(stats.get("ledger_integrity",1.0))==1.0,
    ]
    return "SURVIVES" if all(checks) else "KILLED"
