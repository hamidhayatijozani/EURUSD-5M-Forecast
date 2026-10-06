"""Run rolling real-market 5m experiments on the latest closed candles."""
import json
from datetime import datetime,timezone
from pathlib import Path
from engine.experiments import baseline,pst_signal,cross_asset_signal,combined,resolve,summarize
from engine.live_feed import aligned_closed_series
def run():
    data,times=aligned_closed_series()
    results={}
    for name in ("BASELINE","EXP-006","EXP-007","COMBINATION"):
        returns=[]
        for i in range(12,len(times)-1):
            w={k:v[i-12:i] for k,v in data.items()}
            if name=="BASELINE": s=baseline(w["EURUSD"])
            elif name=="EXP-006": s=pst_signal(w["EURUSD"])
            elif name=="EXP-007": s=cross_asset_signal(w)
            else: s=combined(w)
            returns.append(resolve(s,data["EURUSD"][i],data["EURUSD"][i+1]))
        results[name]=summarize(returns)
    best=max(results,key=lambda k:results[k]["avg_return"])
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"instrument":"EURUSD","timeframe":"5m","windows":len(times)-13,"data_source":"Yahoo Finance research adapter","strategies":results,"best_by_average_return":best,"research_status":"observed_market_data_not_a_profitability_claim"}
    Path("research/results").mkdir(parents=True,exist_ok=True)
    Path("research/results/latest.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps(payload,indent=2))
if __name__=="__main__": run()
