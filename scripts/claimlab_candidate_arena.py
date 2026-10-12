"""Pre-registered alternative EUR/USD 5-minute signal arena."""
from __future__ import annotations
import hashlib, json, math, os
from datetime import timedelta
from pathlib import Path
from statistics import mean, pstdev
import requests
from claimlab.statistics import StatisticalEngine
from claimlab.walkforward import DATASET_URL, dataset_sha256, parse_csv

REGISTRATION_PATH = Path("research/CANDIDATE_ARENA_PREREGISTRATION.json")
OUTPUT_PATH = Path("evidence/candidate-arena/candidate_arena.json")
COSTS = (0.00002, 0.00005, 0.00010)
BLOCK_SIZE = 5
BOOTSTRAP_RESAMPLES = 1000
MIN_TEST_TRADES = 200

def sign(value):
    return 1 if value > 0 else -1 if value < 0 else 0

def _contiguous(rows, start, end):
    return all(rows[i]["timestamp"] - rows[i-1]["timestamp"] == timedelta(minutes=5)
               for i in range(start + 1, end + 1))

def build_observations(rows):
    """Create next-bar targets and signals using only bars closed at issue time."""
    closes = [float(r["close"]) for r in rows]
    close_returns = [None] * len(rows)
    for i in range(1, len(rows)):
        if closes[i-1] <= 0 or closes[i] <= 0:
            raise ValueError("NON_POSITIVE_CLOSE")
        close_returns[i] = closes[i] / closes[i-1] - 1.0
    output = []
    lookback = 24
    for i in range(lookback, len(rows)-1):
        start = i - lookback
        if not _contiguous(rows, start, i+1):
            continue
        features = [float(close_returns[j]) for j in range(i-lookback+1, i+1)]
        last3, last12 = sum(features[-3:]), sum(features[-12:])
        vol24 = pstdev(features)
        z3 = last3 / (vol24 * math.sqrt(3.0)) if vol24 > 0 else 0.0
        prev12 = rows[i-12:i]
        prior_high = max(float(r["high"]) for r in prev12)
        prior_low = min(float(r["low"]) for r in prev12)
        close, opening = float(rows[i]["close"]), float(rows[i]["open"])
        high, low = float(rows[i]["high"]), float(rows[i]["low"])
        body = abs(close-opening)
        upper_wick = high-max(opening,close)
        lower_wick = min(opening,close)-low
        close_location = (close-low)/max(high-low,1e-15)
        wick = 0
        if upper_wick > 2*body and upper_wick > lower_wick and close_location <= .4:
            wick = -1
        elif lower_wick > 2*body and lower_wick > upper_wick and close_location >= .6:
            wick = 1
        positions = {
            "NO_TRADE": 0,
            "MOMENTUM_3": sign(last3),
            "CONTRARIAN_3": -sign(last3),
            "MOMENTUM_12": sign(last12),
            "CONTRARIAN_12": -sign(last12),
            "Z15_MOMENTUM_3": sign(last3) if abs(z3) >= 1.5 else 0,
            "Z15_CONTRARIAN_3": -sign(last3) if abs(z3) >= 1.5 else 0,
            "BREAKOUT_12": 1 if close > prior_high else -1 if close < prior_low else 0,
            "WICK_REVERSAL_1": wick,
        }
        output.append({
            "index": i,
            "issued_at": (rows[i]["timestamp"]+timedelta(minutes=5)).isoformat(),
            "target_at": (rows[i+1]["timestamp"]+timedelta(minutes=5)).isoformat(),
            "actual": float(close_returns[i+1]),
            "positions": positions,
        })
    return output

def _net_rows(rows, candidate, cost):
    values=[]; trades=hits=0; gross_sum=net_sum=0.0; compounded=1.0
    for row in rows:
        position=int(row["positions"][candidate]); actual=float(row["actual"])
        gross=position*actual
        net=gross-cost*abs(position) if position else 0.0
        if position:
            trades += 1
            hits += int(net > 0.0)
        gross_sum += gross; net_sum += net; compounded *= 1.0+net
        values.append(net)
    n=len(rows)
    return {
        "n_bars":n, "trades":trades, "coverage":trades/n if n else 0.0,
        "trade_hit_rate_after_cost":hits/trades if trades else None,
        "gross_return_sum":gross_sum, "net_return_sum":net_sum,
        "net_return_compounded":compounded-1.0,
        "net_return_mean_per_bar":mean(values) if values else 0.0,
        "net_return_mean_per_trade":net_sum/trades if trades else None,
        "net_returns":values,
    }

def run_arena(rows, dataset_text, code_commit):
    registration=json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))
    observations=build_observations(rows)
    if len(observations)<1000:
        raise SystemExit("CANDIDATE_ARENA_INSUFFICIENT_DATA")
    n=len(observations); train_end=int(n*.60); validation_end=int(n*.80)
    validation=observations[train_end:validation_end]; test=observations[validation_end:]
    candidates=registration["candidate_ids"]
    primary={}
    p_values=[]
    for i,candidate in enumerate(candidates):
        metric=_net_rows(test,candidate,COSTS[0])
        inference=StatisticalEngine.block_bootstrap_ci(
            metric.pop("net_returns"), block_size=BLOCK_SIZE,
            resamples=BOOTSTRAP_RESAMPLES, alpha=.05, seed=20261012+i)
        primary[candidate]={
            **metric,
            "ci_lower_net_mean_per_bar":inference["ci_lower"],
            "ci_upper_net_mean_per_bar":inference["ci_upper"],
            "two_sided_block_bootstrap_p_value":inference["p_value"],
            "validation_net_return_sum_at_0_2_pip":_net_rows(validation,candidate,COSTS[0])["net_return_sum"],
            "cost_sensitivity":{
                f"{cost/.0001:.1f}_pip":_net_rows(test,candidate,cost)["net_return_sum"]
                for cost in COSTS
            },
        }
        p_values.append(inference["p_value"])
    rejects=StatisticalEngine.benjamini_hochberg_correction(p_values,alpha=.05)
    for candidate,reject in zip(candidates,rejects):
        m=primary[candidate]; m["bh_reject_at_0_2_pip"]=reject
        m["survives_primary_gate"]=bool(
            candidate!="NO_TRADE" and m["trades"]>=MIN_TEST_TRADES
            and m["ci_lower_net_mean_per_bar"]>0.0 and reject)
    survivors=[name for name in candidates if primary[name]["survives_primary_gate"]]
    return {
        "schema":"claimlab.candidate_arena.v1",
        "status":"COMPUTED_RESEARCH_EVIDENCE",
        "verdict":"SURVIVES" if survivors else "KILLED",
        "surviving_candidates":survivors,
        "registration":registration,
        "dataset":{"url":DATASET_URL,"sha256":dataset_sha256(dataset_text),"rows":len(rows),
                   "first_timestamp":rows[0]["timestamp"].isoformat(),
                   "last_timestamp":rows[-1]["timestamp"].isoformat(),"synthetic":False},
        "execution":{
            "code_commit":code_commit,"valid_observations":n,
            "train_count":train_end,"validation_count":validation_end-train_end,
            "test_count":n-validation_end,
            "train_end_issued_at":observations[train_end-1]["issued_at"],
            "validation_end_issued_at":observations[validation_end-1]["issued_at"],
            "test_start_issued_at":test[0]["issued_at"],"test_end_issued_at":test[-1]["issued_at"],
            "primary_cost":COSTS[0],"cost_sensitivity":list(COSTS),
            "bootstrap_block_size":BLOCK_SIZE,"bootstrap_resamples":BOOTSTRAP_RESAMPLES,
            "multiple_testing":"Benjamini-Hochberg over preregistered candidates"},
        "test_metrics":primary,
        "scientific_boundary":{
            "historical_only":True,"live_performance_verified":False,
            "broker_cost_verified":False,"profitability_established":False,
            "interpretation":"A surviving candidate is eligible for a separate frozen live-paper test; not real-money authorization."},
    }

def main():
    response=requests.get(DATASET_URL,timeout=60); response.raise_for_status()
    text=response.text; rows=parse_csv(text)
    result=run_arena(rows,text,os.getenv("GITHUB_SHA","LOCAL"))
    OUTPUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
