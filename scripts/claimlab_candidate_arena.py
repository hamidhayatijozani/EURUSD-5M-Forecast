"""Pre-registered alternative EUR/USD 5-minute signal arena."""
from __future__ import annotations
import hashlib, json, math, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
import requests
from claimlab.statistics import StatisticalEngine
from claimlab.walkforward import DATASET_URL, dataset_sha256, parse_csv

REGISTRATION_PATH = Path("research/CANDIDATE_ARENA_PREREGISTRATION.json")
RECENT_PREREG_PATH = Path("research/RECENT_OOS_PREREGISTRATION.json")
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
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

def filter_recent_observations(observations, cutoff):
    """Keep forecasts issued at or after a fixed cutoff, without retuning signals."""
    if cutoff.tzinfo is None:
        raise ValueError("OOS_CUTOFF_MUST_BE_TIMEZONE_AWARE")
    return [row for row in observations
            if datetime.fromisoformat(row["issued_at"].replace("Z","+00:00")) >= cutoff]


def fetch_yahoo_5m_rows():
    response=requests.get(
        YAHOO_CHART_URL,
        params={"interval":"5m","range":"60d"},
        headers={"User-Agent":"EURUSD-5M-Forecast/4.0"},
        timeout=45,
    )
    response.raise_for_status()
    raw=response.text
    payload=response.json()
    chart=payload.get("chart",{})
    if chart.get("error"):
        raise RuntimeError(f"YAHOO_CHART_ERROR: {chart['error']}")
    results=chart.get("result") or []
    if not results:
        raise RuntimeError("YAHOO_5M_HISTORY_EMPTY")
    result=results[0]
    timestamps=result.get("timestamp") or []
    quote=(result.get("indicators",{}).get("quote") or [{}])[0]
    rows=[]
    for i,ts in enumerate(timestamps):
        values=[(quote.get(key) or [None]*len(timestamps))[i] for key in ("open","high","low","close")]
        if any(value is None for value in values):
            continue
        rows.append({
            "timestamp":datetime.fromtimestamp(ts,tz=timezone.utc),
            "open":float(values[0]),"high":float(values[1]),
            "low":float(values[2]),"close":float(values[3]),
            "volume":float(((quote.get("volume") or [0]*len(timestamps))[i]) or 0.0),
        })
    rows.sort(key=lambda row:row["timestamp"])
    return rows,raw


def evaluate_fixed_candidates(test_rows,candidates,seed_start=20261012):
    primary={}; p_values=[]
    for i,candidate in enumerate(candidates):
        metric=_net_rows(test_rows,candidate,COSTS[0])
        inference=StatisticalEngine.block_bootstrap_ci(
            metric.pop("net_returns"),block_size=BLOCK_SIZE,
            resamples=BOOTSTRAP_RESAMPLES,alpha=.05,seed=seed_start+i)
        primary[candidate]={
            **metric,
            "ci_lower_net_mean_per_bar":inference["ci_lower"],
            "ci_upper_net_mean_per_bar":inference["ci_upper"],
            "two_sided_block_bootstrap_p_value":inference["p_value"],
            "cost_sensitivity":{
                f"{cost/.0001:.1f}_pip":_net_rows(test_rows,candidate,cost)["net_return_sum"]
                for cost in COSTS},
        }
        p_values.append(inference["p_value"])
    rejects=StatisticalEngine.benjamini_hochberg_correction(p_values,alpha=.05)
    for candidate,reject in zip(candidates,rejects):
        metric=primary[candidate]
        metric["bh_reject_at_0_2_pip"]=reject
        metric["survives_primary_gate"]=bool(
            candidate!="NO_TRADE" and metric["trades"]>=MIN_TEST_TRADES
            and metric["ci_lower_net_mean_per_bar"]>0.0 and reject)
    survivors=[name for name in candidates if primary[name]["survives_primary_gate"]]
    return primary,survivors


def run_recent_oos(yahoo_rows,yahoo_text,historical_sha,code_commit):
    prereg=json.loads(RECENT_PREREG_PATH.read_text(encoding="utf-8"))
    if prereg["historical_dataset_sha256"] != historical_sha:
        raise RuntimeError("RECENT_OOS_HISTORICAL_DATASET_HASH_MISMATCH")
    cutoff=datetime.fromisoformat(prereg["oos_start_at"].replace("Z","+00:00"))
    all_rows=build_observations(yahoo_rows)
    test_rows=filter_recent_observations(all_rows,cutoff)
    if len(test_rows)<1000:
        raise SystemExit(f"RECENT_OOS_INSUFFICIENT_DATA:{len(test_rows)}")
    candidates=prereg["candidate_ids"]
    metrics,survivors=evaluate_fixed_candidates(test_rows,candidates,seed_start=20261013)
    return {
        "experiment_id":prereg["experiment_id"],
        "status":"COMPUTED_RESEARCH_EVIDENCE",
        "verdict":"SURVIVES" if survivors else "KILLED",
        "surviving_candidates":survivors,
        "preregistration":prereg,
        "dataset":{
            "source":"Yahoo Finance chart API",
            "url":YAHOO_CHART_URL+"?interval=5m&range=60d",
            "sha256":hashlib.sha256(yahoo_text.encode("utf-8")).hexdigest(),
            "rows":len(yahoo_rows),
            "first_timestamp":yahoo_rows[0]["timestamp"].isoformat(),
            "last_timestamp":yahoo_rows[-1]["timestamp"].isoformat(),
            "synthetic":False,
        },
        "execution":{
            "code_commit":code_commit,
            "oos_cutoff_issued_at":cutoff.isoformat(),
            "oos_start_issued_at":test_rows[0]["issued_at"],
            "oos_end_issued_at":test_rows[-1]["issued_at"],
            "oos_observation_count":len(test_rows),
            "primary_cost":COSTS[0],
            "cost_sensitivity":list(COSTS),
            "bootstrap_block_size":BLOCK_SIZE,
            "bootstrap_resamples":BOOTSTRAP_RESAMPLES,
            "multiple_testing":"Benjamini-Hochberg over frozen candidate set",
            "parameter_tuning_on_oos":False,
        },
        "test_metrics":metrics,
        "scientific_boundary":{
            "post_cutoff_historical_oos":True,
            "live_performance_verified":False,
            "broker_cost_verified":False,
            "profitability_established":False,
            "interpretation":"Independent post-cutoff historical screen only; no live or broker-cost claim.",
        },
    }


def main():
    response=requests.get(DATASET_URL,timeout=60); response.raise_for_status()
    text=response.text; rows=parse_csv(text)
    result=run_arena(rows,text,os.getenv("GITHUB_SHA","LOCAL"))
    yahoo_rows,yahoo_text=fetch_yahoo_5m_rows()
    result["recent_oos"]=run_recent_oos(
        yahoo_rows,yahoo_text,dataset_sha256(text),os.getenv("GITHUB_SHA","LOCAL"))
    OUTPUT_PATH.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
