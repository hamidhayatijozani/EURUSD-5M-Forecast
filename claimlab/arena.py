"""Same-window strategy arena."""
from statistics import mean

def score(rows,prediction_key="prediction",baseline_key="baseline_prediction"):
    valid=[r for r in rows if r.get("status")=="VALID"]
    if not valid:return {"n":0,"status":"INSUFFICIENT_DATA"}
    mae=mean(abs(float(r["actual"])-float(r[prediction_key])) for r in valid)
    bmae=mean(abs(float(r["actual"])-float(r[baseline_key])) for r in valid)
    net=mean(float(r["friction_adjusted_return"]) for r in valid)
    return {"n":len(valid),"mae":mae,"baseline_mae":bmae,"mae_delta":bmae-mae,
            "friction_adjusted_return":net,"hit_rate":mean(bool(r["direction_hit"]) for r in valid)}

def arena(rows,models):
    return {name:score(rows,key) for name,key in models.items()}
