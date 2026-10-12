"""Exploratory cross-asset pressure arena on post-cutoff EUR/USD data."""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import pstdev
import requests
from scripts.claimlab_candidate_arena import evaluate_fixed_candidates, filter_recent_observations

YAHOO_URL="https://query1.finance.yahoo.com/v8/finance/chart/{}"
TICKERS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","DXY":"DX-Y.NYB"}
REGISTRATION=Path("research/CROSS_ASSET_ARENA_PREREGISTRATION.json")
OUTPUT=Path("evidence/cross-asset-arena/cross_asset_arena.json")
CUTOFF=datetime(2026,9,25,21,0,tzinfo=timezone.utc)


def fetch_symbol(symbol):
    response=requests.get(
        YAHOO_URL.format(TICKERS[symbol]),
        params={"interval":"5m","range":"60d"},
        headers={"User-Agent":"EURUSD-5M-Forecast/4.0"},timeout=45)
    response.raise_for_status()
    raw=response.text; payload=response.json()
    chart=payload.get("chart",{})
    if chart.get("error"):
        raise RuntimeError(f"YAHOO_{symbol}_ERROR:{chart['error']}")
    result=(chart.get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"YAHOO_{symbol}_EMPTY")
    timestamps=result.get("timestamp") or []
    quote=(result.get("indicators",{}).get("quote") or [{}])[0]
    rows=[]
    for i,ts in enumerate(timestamps):
        vals=[(quote.get(k) or [None]*len(timestamps))[i] for k in ("open","high","low","close")]
        if any(v is None for v in vals): continue
        rows.append({"timestamp":datetime.fromtimestamp(ts,tz=timezone.utc),
                     "open":float(vals[0]),"high":float(vals[1]),
                     "low":float(vals[2]),"close":float(vals[3])})
    rows.sort(key=lambda r:r["timestamp"])
    return rows,raw


def _asof(master, auxiliary):
    """At each EURUSD bar, select only an auxiliary candle opened no later than it."""
    aligned=[]; j=0
    for row in master:
        ts=row["timestamp"]
        while j+1<len(auxiliary) and auxiliary[j+1]["timestamp"]<=ts:
            j+=1
        if not auxiliary or auxiliary[j]["timestamp"]>ts or ts-auxiliary[j]["timestamp"]>timedelta(minutes=5):
            aligned.append(None)
        else:
            aligned.append(auxiliary[j])
    return aligned


def build_cross_asset_observations(series):
    master=series["EURUSD"]; n=len(master)
    aligned={"EURUSD":master}
    for symbol in ("GBPUSD","USDJPY","DXY"):
        aligned[symbol]=_asof(master,series[symbol])
    close={s:[r["close"] if r else None for r in rows] for s,rows in aligned.items()}
    returns={s:[None]*n for s in close}
    for s,values in close.items():
        for i in range(1,n):
            if values[i] is None or values[i-1] is None or values[i-1]<=0:
                continue
            ts0=aligned[s][i-1]["timestamp"]; ts1=aligned[s][i]["timestamp"]
            if ts1-ts0 not in (timedelta(0),timedelta(minutes=5)):
                continue
            returns[s][i]=values[i]/values[i-1]-1.0

    output=[]; lookback=24
    for i in range(lookback,n-1):
        # Target must be the next 5-minute close; skip market gaps.
        if any(master[j]["timestamp"]-master[j-1]["timestamp"]!=timedelta(minutes=5)
               for j in range(i-lookback+1,i+2)):
            continue
        needed=("EURUSD","GBPUSD","USDJPY","DXY")
        if any(any(returns[s][j] is None for j in range(i-23,i+1)) for s in needed):
            continue
        r3={s:close[s][i]/close[s][i-3]-1.0 for s in needed}
        z={}
        for s in needed:
            vol=pstdev(returns[s][i-23:i+1])
            z[s]=r3[s]/(vol*3**0.5) if vol>0 else 0.0
        relative=[returns["EURUSD"][j]-returns["GBPUSD"][j] for j in range(i-23,i+1)]
        rel_vol=pstdev(relative)
        rel_z=sum(relative[-3:])/(rel_vol*3**0.5) if rel_vol>0 else 0.0
        votes=[1 if r3["DXY"]<0 else -1 if r3["DXY"]>0 else 0,
               1 if r3["USDJPY"]<0 else -1 if r3["USDJPY"]>0 else 0,
               1 if r3["GBPUSD"]>0 else -1 if r3["GBPUSD"]<0 else 0]
        vote_sum=sum(votes)
        consensus=1 if vote_sum>=2 else -1 if vote_sum<=-2 else 0
        eur_direction=1 if r3["EURUSD"]>0 else -1 if r3["EURUSD"]<0 else 0
        composite=-z["DXY"]-z["USDJPY"]+z["GBPUSD"]
        positions={
            "NO_TRADE":0,
            "CROSS_ASSET_DOLLAR_CONSENSUS":consensus,
            "DXY_LEAD_LAG_3":-1 if r3["DXY"]>0 else 1 if r3["DXY"]<0 else 0,
            "CROSS_ASSET_COMPOSITE_Z15":(1 if composite>0 else -1) if abs(composite)>=1.5 else 0,
            "EUR_GBP_DIVERGENCE_CONTRARIAN":(-1 if rel_z>0 else 1) if abs(rel_z)>=1.5 else 0,
            "EURUSD_MOMENTUM_CONFIRMED":eur_direction if consensus and eur_direction==consensus else 0,
            "EURUSD_CROSS_ASSET_CATCHUP":(1 if consensus>0 else -1) if abs(rel_z)>=1.5 and consensus and ((rel_z<0 and consensus>0) or (rel_z>0 and consensus<0)) else 0,
        }
        output.append({
            "index":i,
            "issued_at":(master[i]["timestamp"]+timedelta(minutes=5)).isoformat(),
            "target_at":(master[i+1]["timestamp"]+timedelta(minutes=5)).isoformat(),
            "actual":close["EURUSD"][i+1]/close["EURUSD"][i]-1.0,
            "positions":positions,
        })
    return output


def main():
    prereg=json.loads(REGISTRATION.read_text(encoding="utf-8"))
    if prereg["oos_start_at"]!="2026-09-25T21:00:00Z":
        raise RuntimeError("CROSS_ASSET_CUTOFF_MISMATCH")
    series={}; raw_hashes={}
    for symbol in TICKERS:
        series[symbol],raw=fetch_symbol(symbol)
        raw_hashes[symbol]=hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if any(len(series[s])<1000 for s in TICKERS):
        raise SystemExit("CROSS_ASSET_HISTORY_INSUFFICIENT")
    all_rows=build_cross_asset_observations(series)
    test=filter_recent_observations(all_rows,CUTOFF)
    if len(test)<500:
        raise SystemExit(f"CROSS_ASSET_OOS_INSUFFICIENT:{len(test)}")
    candidates=prereg["candidate_ids"]
    metrics,survivors=evaluate_fixed_candidates(test,candidates,seed_start=20261014)
    result={
        "schema":"claimlab.cross_asset_arena.v1",
        "status":"COMPUTED_EXPLORATORY_RESEARCH",
        "verdict":"EXPLORATORY_SURVIVES" if survivors else "KILLED",
        "surviving_candidates":survivors,
        "registration":prereg,
        "data":{"source":"Yahoo Finance 5-minute chart API","tickers":TICKERS,
                "row_counts":{k:len(v) for k,v in series.items()},"sha256_by_symbol":raw_hashes,
                "oos_start_issued_at":test[0]["issued_at"],"oos_end_issued_at":test[-1]["issued_at"],
                "oos_observations":len(test),"synthetic":False},
        "execution":{"code_commit":os.getenv("GITHUB_SHA","LOCAL"),"primary_cost":0.00002,
                     "cost_sensitivity":[0.00002,0.00005,0.0001],
                     "bootstrap_block_size":5,"bootstrap_resamples":1000,
                     "multiple_testing":"Benjamini-Hochberg across frozen cross-asset candidates",
                     "parameter_tuning_on_oos":False},
        "test_metrics":metrics,
        "scientific_boundary":{"exploratory_only":True,"live_performance_verified":False,
            "broker_cost_verified":False,"profitability_established":False,
            "interpretation":"Even an exploratory survivor requires a new frozen forward-paper test; no real-money claim."}
    }
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
