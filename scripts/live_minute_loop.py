"""Every-minute real-market five-minute forecast, deep pattern analysis and adaptive learning."""
import json, os, subprocess, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from engine.algorithm_factory import adaptive_ensemble, update_algorithm_stats, Candidate
from engine.experiments import combined
from engine.context import collect_external_context
from engine.live_feed import aligned_closed_1m_series, aligned_closed_1m_ohlc

STATE_PATH=Path("research/live_state.json")
PRED_PATH=Path("research/live_predictions.jsonl")
FRICTION=0.00002
HORIZON=5
SLEEP_SECONDS=60

def iso(dt): return dt.astimezone(timezone.utc).isoformat()
def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {
        "bias":0.0,"resolved":0,"correct":0,"errors":[],"last_prediction":None,
        "context_cycles":0,"algorithms":{}
    }
def save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8")
def read_predictions():
    if not PRED_PATH.exists(): return []
    return [json.loads(x) for x in PRED_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
def save_predictions(rows):
    PRED_PATH.parent.mkdir(parents=True,exist_ok=True)
    PRED_PATH.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in rows),encoding="utf-8")

def predict(series,ohlc,state,context):
    if any(len(v)<30 for v in series.values()) or len(ohlc)<30:
        raise RuntimeError("need at least 30 closed one-minute candles and OHLC")
    base=combined(series)
    algo_score,_,candidates=adaptive_ensemble(series["EURUSD"],ohlc,state)
    adjusted=0.55*base.score+0.45*algo_score+0.18*context["context_score"]+state["bias"]
    if abs(context["power_score"])>=0.60: adjusted*=0.80
    adjusted=max(-1.0,min(1.0,adjusted))
    direction="UP" if adjusted>0.12 else "DOWN" if adjusted<-0.12 else "FLAT"
    predicted_return=adjusted*0.0005
    return base,direction,adjusted,predicted_return,candidates

def settle(rows,latest_ts,latest_price,state):
    changed=False
    for row in rows:
        if row.get("resolved_at") or datetime.fromisoformat(row["target_ts"])>latest_ts: continue
        actual=latest_price/row["entry_price"]-1.0
        predicted=row["predicted_return"]; error=actual-predicted
        state["bias"]=max(-0.5,min(0.5,0.90*state["bias"]+0.10*error/0.0005))
        hit=((predicted>0 and actual>FRICTION) or (predicted<0 and actual<-FRICTION) or
             (abs(predicted)<=FRICTION and abs(actual)<=FRICTION))
        candidates=[Candidate(x["name"],x["score"],x["predicted_return"]) for x in row.get("algorithms",[])]
        if candidates: update_algorithm_stats(state,candidates,actual)
        state["resolved"]+=1; state["correct"]+=int(hit)
        state["errors"].append(error); state["errors"]=state["errors"][-500:]
        row.update(actual_return=actual,error=error,hit=hit,resolved_at=iso(latest_ts),status="RESOLVED")
        changed=True
    return changed

def git_commit():
    if not os.environ.get("GITHUB_ACTIONS"): return
    subprocess.run(["git","config","user.name","github-actions[bot]"],check=False)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=False)
    subprocess.run(["git","add",str(STATE_PATH),str(PRED_PATH)],check=False)
    if subprocess.run(["git","diff","--cached","--quiet"]).returncode==0: return
    subprocess.run(["git","commit","-m","chore: persist live forecast evidence [skip ci]"],check=False)
    subprocess.run(["git","push"],check=False)

def cycle():
    now=datetime.now(timezone.utc)
    data,times=aligned_closed_1m_series(now)
    ohlc_map,ohlc_times=aligned_closed_1m_ohlc(now)
    if ohlc_times[-1]!=times[-1]: raise RuntimeError("OHLC and close information locks are not aligned")
    latest_ts=times[-1]; latest_price=data["EURUSD"][-1]
    state=load_state(); predictions=read_predictions()
    changed=settle(predictions,latest_ts,latest_price,state)
    if state.get("last_prediction")!=iso(latest_ts):
        series={k:v[-60:] for k,v in data.items()}
        context=collect_external_context(list(zip(times[-120:],data["EURUSD"][-120:])),now=latest_ts)
        signal,direction,score,predicted_return,candidates=predict(series,ohlc_map["EURUSD"][-60:],state,context)
        row={"prediction_ts":iso(latest_ts),"target_ts":iso(latest_ts+timedelta(minutes=HORIZON)),
             "entry_price":latest_price,"direction":direction,"score":score,
             "confidence":signal.confidence,"regime":signal.regime,"contradiction":signal.contradiction,
             "predicted_return":predicted_return,
             "algorithms":[{"name":c.name,"score":c.score,"predicted_return":c.predicted_return} for c in candidates],
             "external_context":context,"status":"PENDING",
             "engine":"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+PST+CROSS-ASSET+NEWS+TOP50-24H+DATACENTER-POWER+ONLINE-CALIBRATION"}
        predictions.append(row); state["last_prediction"]=iso(latest_ts)
        state["context_cycles"]=state.get("context_cycles",0)+1
        state["last_external_context"]=context; changed=True
        print(json.dumps(row,sort_keys=True))
    state["last_cycle_at"]=iso(datetime.now(timezone.utc))
    state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None
    save_predictions(predictions); save_state(state)
    if changed: git_commit()

def main():
    for i in range(int(os.environ.get("LIVE_CYCLES","5"))):
        try: cycle()
        except Exception as exc: print(f"LIVE_CYCLE_ERROR: {type(exc).__name__}: {exc}")
        if i+1<int(os.environ.get("LIVE_CYCLES","5")): time.sleep(SLEEP_SECONDS)

if __name__=="__main__": main()
