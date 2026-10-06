"""Every-minute real-market five-minute forecast, verification and online learning."""
import json, os, subprocess, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.context import collect_external_context
from engine.experiments import combined
from engine.live_feed import aligned_closed_1m_series

STATE_PATH=Path("research/live_state.json")
PRED_PATH=Path("research/live_predictions.jsonl")
FRICTION=0.00002
HORIZON=5
SLEEP_SECONDS=60

def iso(dt): return dt.astimezone(timezone.utc).isoformat()

def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {
        "bias":0.0,"resolved":0,"correct":0,"errors":[],"last_prediction":None,
        "context_cycles":0
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

def predict(series,state,context):
    if any(len(v)<12 for v in series.values()):
        raise RuntimeError("need at least 12 closed one-minute candles for all assets")
    s=combined(series)
    # External context is deliberately capped. Price structure remains primary.
    adjusted=s.score + 0.18*context["context_score"] + state["bias"]
    # Infrastructure stress changes conviction, not direction.
    if abs(context["power_score"]) >= 0.60:
        adjusted *= 0.80
    adjusted=max(-1.0,min(1.0,adjusted))
    direction="UP" if adjusted>0.12 else "DOWN" if adjusted<-0.12 else "FLAT"
    predicted_return=adjusted*0.0005
    return s,direction,adjusted,predicted_return

def settle(rows,latest_ts,latest_price,state):
    changed=False
    for row in rows:
        if row.get("resolved_at") or datetime.fromisoformat(row["target_ts"])>latest_ts:
            continue
        actual=latest_price/row["entry_price"]-1.0
        predicted=row["predicted_return"]
        error=actual-predicted
        state["bias"]=max(-0.5,min(0.5,0.90*state["bias"]+0.10*error/0.0005))
        hit=((predicted>0 and actual>FRICTION) or
             (predicted<0 and actual<-FRICTION) or
             (abs(predicted)<=FRICTION and abs(actual)<=FRICTION))
        state["resolved"]+=1
        state["correct"]+=int(hit)
        state["errors"].append(error)
        state["errors"]=state["errors"][-500:]
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
    data,times=aligned_closed_1m_series(datetime.now(timezone.utc))
    latest_ts=times[-1]
    latest_price=data["EURUSD"][-1]
    state=load_state()
    predictions=read_predictions()
    changed=settle(predictions,latest_ts,latest_price,state)

    if state.get("last_prediction")!=iso(latest_ts):
        series={k:v[-60:] for k,v in data.items()}
        context=collect_external_context(
            list(zip([t for t in times[-120:]], data["EURUSD"][-120:])),
            now=latest_ts
        )
        signal,direction,score,predicted_return=predict(series,state,context)
        row={
            "prediction_ts":iso(latest_ts),
            "target_ts":iso(latest_ts+timedelta(minutes=HORIZON)),
            "entry_price":latest_price,
            "direction":direction,"score":score,
            "confidence":signal.confidence,"regime":signal.regime,
            "contradiction":signal.contradiction,
            "predicted_return":predicted_return,
            "external_context":context,
            "status":"PENDING",
            "engine":"COMBINATION+NEWS+TOP50-24H-TRADERS+DATACENTER-POWER+ONLINE-CALIBRATION"
        }
        predictions.append(row)
        state["last_prediction"]=iso(latest_ts)
        state["context_cycles"]=state.get("context_cycles",0)+1
        state["last_external_context"]=context
        changed=True
        print(json.dumps(row,sort_keys=True))

    state["last_cycle_at"]=iso(datetime.now(timezone.utc))
    state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None
    save_predictions(predictions)
    save_state(state)
    if changed: git_commit()

def main():
    cycles=int(os.environ.get("LIVE_CYCLES","5"))
    for i in range(cycles):
        try: cycle()
        except Exception as exc: print(f"LIVE_CYCLE_ERROR: {type(exc).__name__}: {exc}")
        if i+1<cycles: time.sleep(SLEEP_SECONDS)

if __name__=="__main__": main()
