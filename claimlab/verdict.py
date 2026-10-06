"""Verdict evaluation against the canonical locked registry."""
from operator import eq, ge, gt, le, lt
from .registry import assert_locked, load_registry

OPS = {">": gt, ">=": ge, "<": lt, "<=": le, "=": eq}


def verdict(stats, registry=None, min_n=None):
    r = registry or load_registry()
    if registry is None:
        assert_locked()
    n = int(stats.get("n", 0))
    minimum = int(min_n if min_n is not None else r["minimum_n"])
    if n < minimum:
        return "INSUFFICIENT_DATA"

    for claim in r["claims"]:
        metric = claim["metric"]
        key = claim.get("decision_metric", "value")
        if key == "ci_lower":
            value = stats.get(f"{metric}_ci_lower", float("nan"))
            if value != value:
                return "KILLED"
        else:
            value = stats.get(metric, claim["threshold"])
        if claim["family"] == "performance":
            if not stats.get("bh_reject", {}).get(claim["id"], False):
                return "KILLED"
        if not OPS[claim["direction"]](float(value), float(claim["threshold"])):
            return "KILLED"
    return "SURVIVES"
