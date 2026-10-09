"""Every-minute real-market 5-minute forecasting with exact-target resolution and ClaimLab evidence."""
import json, os, subprocess, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from engine.algorithm_factory import adaptive_ensemble, update_algorithm_stats, Candidate
from engine.experiments import combined, pst_signal
from engine.context import collect_external_context
from engine.forecast import forecast
from engine.live_feed import aligned_closed_1m_series, aligned_closed_1m_ohlc
from claimlab.ledger import Ledger
from claimlab.registry import registry_hash
from claimlab.resolver import resolve
from claimlab.schema import Observation

STATE_PATH=Path("research/live_state.json")
PRED_PATH=Path("research/live_predictions.jsonl")
CLAIM_LEDGER_PATH=Path("research/claimlab_live_observations.jsonl")
FRICTION=0.00002
HORIZON=5
SLEEP_SECONDS=60
LIVE_DATA_CONTRACT_VERSION="freshness-90s-v2"

def iso(dt): return dt.astimezone(timezone.utc).isoformat()
def load_state():
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {"bias":0.0,"resolved":0,"correct":0,"errors":[],"last_prediction":None,"context_cycles":0,"algorithms":{}}
def save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); STATE_PATH.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8")
def read_predictions():
    if not PRED_PATH.exists(): return []
    return [json.loads(x) for x in PRED_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
def save_predictions(rows):
    PRED_PATH.parent.mkdir(parents=True,exist_ok=True)
    PRED_PATH.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in rows),encoding="utf-8")

def _price_map(times,prices):
    return {iso(t):float(p) for t,p in zip(times,prices)}

def predict(series,ohlc,state,context):
    if any(len(v)<30 for v in series.values()) or len(ohlc)<30: raise RuntimeError("need at least 30 closed one-minute candles and OHLC")
    base=(combined(series) if all(k in series for k in ("EURUSD","GBPUSD","USDJPY","DXY"))
          else pst_signal(series["EURUSD"]))
    base_forecast=forecast(series["EURUSD"])
    algo_score,_,candidates=adaptive_ensemble(series["EURUSD"],ohlc,state)
    adjusted=0.55*base.score+0.45*algo_score+0.18*context["context_score"]+state["bias"]
    if abs(context["power_score"])>=0.60: adjusted*=0.80
    adjusted=max(-1.0,min(1.0,adjusted))
    direction="UP" if adjusted>0.12 else "DOWN" if adjusted<-0.12 else "FLAT"
    predicted_return=adjusted*0.0005
    return base,direction,adjusted,predicted_return,candidates,base_forecast.score

def _freshness_age_seconds(source_candle_open, observed_at):
    """Measure age from candle close, not candle open; OHLC timestamps label opens."""
    source_candle_close = source_candle_open + timedelta(minutes=1)
    return max(0.0, (observed_at - source_candle_close).total_seconds())


def _prediction_times(latest_bar_open):
    """Translate 1m candle-open labels to exact close/issue/target event times."""
    issued_at=latest_bar_open+timedelta(minutes=1)
    target_bar_open=latest_bar_open+timedelta(minutes=HORIZON)
    target_at=target_bar_open+timedelta(minutes=1)
    return issued_at,target_bar_open,target_at


def _quarantine_legacy_predictions(rows):
    changed=False
    for row in rows:
        if row.get("data_contract_version") != LIVE_DATA_CONTRACT_VERSION and row.get("status")=="PENDING":
            row.update(status="EXCLUDED_PRE_CONTRACT",
                       excluded_reason="Prediction predates freshness-checked timing contract")
            changed=True
    return changed


def settle(rows,times,prices,state,code_commit):
    changed=_quarantine_legacy_predictions(rows)
    price_map=_price_map(times,prices)
    for row in rows:
        # Never backfill pre-contract predictions into the clean evidence ledger.
        if row.get("data_contract_version") != LIVE_DATA_CONTRACT_VERSION:
            continue
        if row.get("resolved_at"): continue
        target=row["target_ts"]  # candle-open key for price lookup
        if target not in price_map: continue
        actual=price_map[target]/float(row["entry_price"])-1.0
        predicted=float(row["predicted_return"]); baseline=float(row["baseline_prediction"])
        error=actual-predicted
        target_dt=datetime.fromisoformat(target.replace("Z","+00:00"))
        resolved_at=iso(target_dt+timedelta(minutes=1))
        if row.get("target_at") != resolved_at:
            raise RuntimeError("LIVE_TARGET_CLOSE_TIMESTAMP_MISMATCH")
        obs=resolve({
          "schema_version":"claimlab.observation.v1","prediction_id":row["prediction_id"],
          "issued_at":row["prediction_ts"],"target_at":row["target_at"],
          "feature_cutoff_at":row["prediction_ts"],
          "symbol":"EURUSD","horizon_seconds":HORIZON*60,"prediction":predicted,"code_commit":code_commit,
          "config_hash": row["config_hash"],
          "claim_registry_hash": registry_hash(),
          "provider": row.get("provider", "Yahoo"),
          "source_candle_ts": row.get("source_candle_ts", row["prediction_ts"]),
          "observed_at": row.get("observed_at", row["prediction_ts"]),
          "data_age_seconds": float(row.get("data_age_seconds", 0.0)),
          "freshness_limit_seconds": float(row.get("freshness_limit_seconds", 90.0)),
          "freshness_status": row.get("freshness_status", "FRESH")},
          actual=actual,baseline_prediction=baseline,
          resolved_at=resolved_at,friction=(FRICTION,0.0,0.0))
        ledger=Ledger(CLAIM_LEDGER_PATH)
        ledger.append(Observation(**obs))
        if not ledger.verify():
            raise RuntimeError("LIVE_CLAIM_LEDGER_INTEGRITY_FAILURE")
        state["bias"]=max(-0.5,min(0.5,0.90*state["bias"]+0.10*error/0.0005))
        hit=((predicted>0 and actual>FRICTION) or (predicted<0 and actual<-FRICTION))
        candidates=[Candidate(x["name"],x["score"],x["predicted_return"]) for x in row.get("algorithms",[])]
        if candidates: update_algorithm_stats(state,candidates,actual)
        state["resolved"]+=1; state["correct"]+=int(hit); state["errors"].append(error); state["errors"]=state["errors"][-500:]
        row.update(actual_return=actual,error=error,hit=hit,resolved_at=resolved_at,status="RESOLVED")
        changed=True
    return changed

def git_commit():
    if not os.environ.get("GITHUB_ACTIONS"): return
    subprocess.run(["git","config","user.name","github-actions[bot]"],check=False)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=False)
    evidence_paths=[p for p in (STATE_PATH,PRED_PATH,CLAIM_LEDGER_PATH) if p.exists()]
    if not evidence_paths:return
    subprocess.run(["git","add",*[str(p) for p in evidence_paths]],check=True)
    if subprocess.run(["git","diff","--cached","--quiet"]).returncode==0:return
    subprocess.run(["git","commit","-m","chore: persist live ClaimLab evidence [skip ci]"],check=True)
    # Never report a successful live cycle when its evidence failed to persist.
    subprocess.run(["git","push"],check=True)

def cycle():
    now=datetime.now(timezone.utc); data,times=aligned_closed_1m_series(now); ohlc_map,ohlc_times=aligned_closed_1m_ohlc(now)
    # The two HTTP fetches can straddle a minute boundary. Join only timestamps
    # present in both snapshots; never pair prices from different bars.
    common=sorted(set(times).intersection(ohlc_times))
    if len(common)<30:
        raise RuntimeError("fewer than 30 common close/OHLC timestamps")
    close_index={ts:i for i,ts in enumerate(times)}
    ohlc_index={ts:i for i,ts in enumerate(ohlc_times)}
    data={k:[v[close_index[ts]] for ts in common] for k,v in data.items()}
    ohlc_map={k:[v[ohlc_index[ts]] for ts in common] for k,v in ohlc_map.items()}
    times=ohlc_times=common
    latest_ts = times[-1]
    latest_price = data["EURUSD"][-1]
    # Yahoo timestamps label candle opens. Measure freshness from the
    # source candle timestamp to the actual observation time.
    source_candle_ts = latest_ts
    observed_at = datetime.now(timezone.utc)
    data_age_seconds = _freshness_age_seconds(source_candle_ts, observed_at)
    if data_age_seconds > 90:
        raise RuntimeError(f"STALE_EURUSD_FRESHNESS_EVIDENCE:{data_age_seconds:.1f}s")
    state = load_state()
    predictions = read_predictions()
    prices= data["EURUSD"]; changed=settle(predictions,times,prices,state,os.environ.get("GITHUB_SHA","LOCAL"))
    if state.get("last_prediction")!=iso(latest_ts):
        series={k:v[-60:] for k,v in data.items()}; context=collect_external_context(list(zip(times[-120:],data["EURUSD"][-120:])),now=latest_ts)
        signal,direction,score,predicted_return,candidates,baseline_prediction=predict(series,ohlc_map["EURUSD"][-60:],state,context)
        cross_asset_enabled=all(k in series for k in ("GBPUSD","USDJPY","DXY"))
        config={"engine":f"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+{signal.name}",
                "cross_asset_enabled":cross_asset_enabled,
                "horizon_seconds":300,"friction":FRICTION}
        import hashlib
        config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        issued_at,target_bar_open,target_at=_prediction_times(latest_ts)
        row={"prediction_id":f"live-eurusd-1m-{latest_ts.strftime('%Y%m%dT%H%M%SZ')}","prediction_ts":iso(issued_at),
          "target_ts":iso(target_bar_open),"target_at":iso(target_at),
          "data_contract_version":LIVE_DATA_CONTRACT_VERSION,
          "entry_price":latest_price,"direction":direction,"score":score,"confidence":signal.confidence,"regime":signal.regime,"contradiction":signal.contradiction,
          "predicted_return":predicted_return,"baseline_prediction":baseline_prediction,
          "algorithms":[{"name":c.name,"score":c.score,"predicted_return":c.predicted_return} for c in candidates],"external_context":context,
          "config_hash":config_hash,"status":"PENDING","cross_asset_enabled":cross_asset_enabled,
          "provider":"Yahoo","source_candle_ts":iso(source_candle_ts),"observed_at":iso(observed_at),
          "data_age_seconds":data_age_seconds,"freshness_limit_seconds":90.0,"freshness_status":"FRESH",
          "engine":f"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+{signal.name}+NEWS+TOP50-24H+DATACENTER-POWER+ONLINE-CALIBRATION"}
        predictions.append(row); state["last_prediction"]=iso(latest_ts); state["context_cycles"]=state.get("context_cycles",0)+1; state["last_external_context"]=context; changed=True; print(json.dumps(row,sort_keys=True))
    state["last_cycle_at"]=iso(datetime.now(timezone.utc)); state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None
    save_predictions(predictions); save_state(state)
    if changed: git_commit()

def main():
    cycles=int(os.environ.get("LIVE_CYCLES","5"))
    successful=0
    for i in range(cycles):
        try:
            cycle()
            successful+=1
        except Exception as exc:
            print(f"LIVE_CYCLE_ERROR: {type(exc).__name__}: {exc}")
        if i+1<cycles:
            time.sleep(SLEEP_SECONDS)
    if successful==0:
        raise SystemExit("NO_SUCCESSFUL_LIVE_CYCLES")
if __name__=="__main__": main()
