"""Preregistered ClaimLab verdicts."""
def verdict(stats,min_n=100):
    n=int(stats.get("n",0))
    if n<min_n:return "INSUFFICIENT_DATA"
    if stats.get("mae_delta",0)>0 and stats.get("friction_adjusted_return",0)>0:return "SURVIVES"
    return "KILLED"
