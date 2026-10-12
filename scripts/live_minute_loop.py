"""Every-minute real-market 5-minute forecasting with exact-target resolution and ClaimLab evidence."""
import hashlib, json, os, subprocess, time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from pathlib import Path
from statistics import pstdev
from engine.algorithm_factory import adaptive_ensemble, update_algorithm_stats, Candidate
from engine.experiments import combined, pst_signal
from engine.context import collect_external_context
from engine.forecast import forecast
from engine.forecast_evidence import build_decision_evidence, verify_decision_evidence
from engine.live_feed import aligned_closed_1m_series, aligned_closed_1m_ohlc, closed_1m_rows
from claimlab.ledger import Ledger
from claimlab.registry import registry_hash
from claimlab.resolver import resolve
from claimlab.schema import Observation

STATE_PATH=Path("research/live_state.json")
PRED_PATH=Path("research/live_predictions.jsonl")
CLAIM_LEDGER_PATH=Path("research/claimlab_live_observations.jsonl")
CROSS_ASSET_LEDGER_PATH=Path("research/cross_asset_live_observations.jsonl")
CROSS_ASSET_CONTRACT_VERSION="live-1m-signals-to-5m-target-v1"
CROSS_ASSET_CONTRACT_VERSION_V2="live-1m-gbpusd-usdjpy-to-5m-target-v2"
CROSS_ASSET_CANDIDATES_V2=("LIVE1M2_NO_TRADE","LIVE1M2_USDJPY_INVERSE_3M","LIVE1M2_GBPUSD_MOMENTUM_3M","LIVE1M2_GBPUSD_USDJPY_CONSENSUS_3M","LIVE1M2_EURUSD_MOMENTUM_CONFIRMED_2SOURCE","LIVE1M2_EUR_GBP_DIVERGENCE_Z15","LIVE1M2_EURUSD_CATCHUP_2SOURCE")
CROSS_ASSET_CANDIDATES=("LIVE1M_NO_TRADE","LIVE1M_DOLLAR_CONSENSUS_3M","LIVE1M_DXY_INVERSE_3M","LIVE1M_COMPOSITE_Z15","LIVE1M_EUR_GBP_DIVERGENCE_Z15","LIVE1M_EURUSD_MOMENTUM_CONFIRMED","LIVE1M_EURUSD_CATCHUP")
FRICTION=0.00002
HORIZON=5
SLEEP_SECONDS=35
LIVE_DATA_CONTRACT_VERSION="freshness-90s-v2"

def iso(dt): return dt.astimezone(timezone.utc).isoformat()
def load_state():
    defaults={"bias":0.0,"resolved":0,"correct":0,"errors":[],"last_prediction":None,
              "context_cycles":0,"algorithms":{},
              "live_data_contract_version":LIVE_DATA_CONTRACT_VERSION,"accuracy":None}
    if not STATE_PATH.exists():
        return defaults
    state=json.loads(STATE_PATH.read_text())
    if state.get("live_data_contract_version") != LIVE_DATA_CONTRACT_VERSION:
        # Old counters include pre-contract predictions that are deliberately
        # excluded from the clean ClaimLab ledger. Archive their summary, then
        # restart online calibration and headline metrics for the current contract.
        if "legacy_pre_contract_metrics" not in state and any(
            state.get(key) for key in ("resolved","correct","errors","algorithms")
        ):
            state["legacy_pre_contract_metrics"]={
                "resolved":state.get("resolved",0),
                "correct":state.get("correct",0),
                "accuracy":state.get("accuracy"),
                "note":"Unscoped legacy metrics; not comparable to freshness-90s-v2 evidence",
            }
        state.update({
            "live_data_contract_version":LIVE_DATA_CONTRACT_VERSION,
            "bias":0.0,"resolved":0,"correct":0,"errors":[],
            "algorithms":{},"context_cycles":0,"accuracy":None,
        })
        _reconcile_current_contract_metrics(state)
    return state
def _reconcile_current_contract_metrics(state):
    """Rebuild headline counters from resolved predictions backed by the verified ledger."""
    predictions=read_predictions()
    ledger=Ledger(CLAIM_LEDGER_PATH)
    ledger_rows=ledger._rows()
    if ledger_rows and not ledger.verify():
        raise RuntimeError("LIVE_CLAIM_LEDGER_INTEGRITY_FAILURE_DURING_METRIC_REBUILD")
    ledger_ids={row.get("prediction_id") for row in ledger_rows}
    resolved=[row for row in predictions
              if row.get("data_contract_version")==LIVE_DATA_CONTRACT_VERSION
              and row.get("status")=="RESOLVED"]
    missing=[row.get("prediction_id") for row in resolved
             if row.get("prediction_id") not in ledger_ids]
    if missing:
        raise RuntimeError(
            "LIVE_STATE_LEDGER_MISMATCH: resolved current-contract predictions "
            f"missing from ledger: {missing[:5]}"
        )
    state["resolved"]=len(resolved)
    state["correct"]=sum(bool(row.get("hit")) for row in resolved)
    state["errors"]=[float(row["error"]) for row in resolved if "error" in row][-500:]
    state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); STATE_PATH.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8")
def read_predictions():
    if not PRED_PATH.exists(): return []
    return [json.loads(x) for x in PRED_PATH.read_text(encoding="utf-8").splitlines() if x.strip()]
def save_predictions(rows):
    PRED_PATH.parent.mkdir(parents=True,exist_ok=True)
    PRED_PATH.write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in rows),encoding="utf-8")

def _sign(value):
    return 1 if value>0 else -1 if value<0 else 0


def cross_asset_candidates(series):
    """Freeze each candidate only when its own required inputs are aligned."""
    positions={name:None for name in CROSS_ASSET_CANDIDATES}
    positions["LIVE1M_NO_TRADE"]=0
    required=("EURUSD","GBPUSD","USDJPY","DXY")
    available={symbol for symbol in required if symbol in series and len(series[symbol])>=30}
    returns={}
    for symbol in available:
        prices=[float(x) for x in series[symbol]]
        returns[symbol]=[prices[i]/prices[i-1]-1.0 for i in range(1,len(prices))]
    recent={symbol:values[-24:] for symbol,values in returns.items()}
    r3={symbol:sum(values[-3:]) for symbol,values in recent.items()}
    z={}
    for symbol,values in recent.items():
        vol=pstdev(values)
        z[symbol]=sum(values[-3:])/(vol*(3.0**0.5)) if vol>0 else 0.0

    # DXY inverse is a single-source candidate and remains testable even when
    # other auxiliary feeds are absent.
    if "DXY" in available:
        positions["LIVE1M_DXY_INVERSE_3M"]=-_sign(r3["DXY"])

    rel_z=None
    if {"EURUSD","GBPUSD"}.issubset(available):
        rel=[a-b for a,b in zip(recent["EURUSD"],recent["GBPUSD"])]
        rel_vol=pstdev(rel)
        rel_z=sum(rel[-3:])/(rel_vol*(3.0**0.5)) if rel_vol>0 else 0.0
        positions["LIVE1M_EUR_GBP_DIVERGENCE_Z15"]=-_sign(rel_z) if abs(rel_z)>=1.5 else 0

    consensus=None
    if {"DXY","USDJPY","GBPUSD"}.issubset(available):
        votes=[_sign(-r3["DXY"]),_sign(-r3["USDJPY"]),_sign(r3["GBPUSD"])]
        vote_sum=sum(votes)
        consensus=1 if vote_sum>=2 else -1 if vote_sum<=-2 else 0
        composite=-z["DXY"]-z["USDJPY"]+z["GBPUSD"]
        positions["LIVE1M_DOLLAR_CONSENSUS_3M"]=consensus
        positions["LIVE1M_COMPOSITE_Z15"]=_sign(composite) if abs(composite)>=1.5 else 0

    if consensus is not None and "EURUSD" in available:
        eur_direction=_sign(r3["EURUSD"])
        positions["LIVE1M_EURUSD_MOMENTUM_CONFIRMED"]=(
            eur_direction if consensus and eur_direction==consensus else 0)
        if rel_z is not None:
            positions["LIVE1M_EURUSD_CATCHUP"]=(
                consensus if abs(rel_z)>=1.5 and consensus and
                ((rel_z<0 and consensus>0) or (rel_z>0 and consensus<0)) else 0)

    active_available=any(value is not None for key,value in positions.items() if key!="LIVE1M_NO_TRADE")
    if not active_available:
        status="UNAVAILABLE_MISSING_CROSS_ASSET_HISTORY"
    elif len(available)==len(required):
        status="READY"
    else:
        status="READY_PARTIAL"
    return positions,status



def cross_asset_candidates_v2(series):
    """Frozen two-FX-pair family; does not depend on the unavailable DXY feed."""
    positions={name:None for name in CROSS_ASSET_CANDIDATES_V2}
    positions["LIVE1M2_NO_TRADE"]=0
    required=("EURUSD","GBPUSD","USDJPY")
    available={symbol for symbol in required if symbol in series and len(series[symbol])>=30}
    returns={}
    for symbol in available:
        prices=[float(x) for x in series[symbol]]
        returns[symbol]=[prices[i]/prices[i-1]-1.0 for i in range(1,len(prices))]
    recent={symbol:values[-24:] for symbol,values in returns.items()}
    r3={symbol:sum(values[-3:]) for symbol,values in recent.items()}
    if "USDJPY" in available:
        positions["LIVE1M2_USDJPY_INVERSE_3M"]=-_sign(r3["USDJPY"])
    if "GBPUSD" in available:
        positions["LIVE1M2_GBPUSD_MOMENTUM_3M"]=_sign(r3["GBPUSD"])

    consensus=None
    if {"GBPUSD","USDJPY"}.issubset(available):
        votes=[-_sign(r3["USDJPY"]),_sign(r3["GBPUSD"])]
        consensus=1 if sum(votes)==2 else -1 if sum(votes)==-2 else 0
        positions["LIVE1M2_GBPUSD_USDJPY_CONSENSUS_3M"]=consensus
        eur_direction=_sign(r3["EURUSD"]) if "EURUSD" in available else 0
        positions["LIVE1M2_EURUSD_MOMENTUM_CONFIRMED_2SOURCE"]=(
            eur_direction if consensus and eur_direction==consensus else 0)

    rel_z=None
    if {"EURUSD","GBPUSD"}.issubset(available):
        relative=[a-b for a,b in zip(recent["EURUSD"],recent["GBPUSD"])]
        rel_vol=pstdev(relative)
        rel_z=sum(relative[-3:])/(rel_vol*(3.0**0.5)) if rel_vol>0 else 0.0
        positions["LIVE1M2_EUR_GBP_DIVERGENCE_Z15"]=-_sign(rel_z) if abs(rel_z)>=1.5 else 0
        if consensus is not None:
            positions["LIVE1M2_EURUSD_CATCHUP_2SOURCE"]=(
                consensus if abs(rel_z)>=1.5 and consensus and
                ((rel_z<0 and consensus>0) or (rel_z>0 and consensus<0)) else 0)

    active_available=any(value is not None for key,value in positions.items() if key!="LIVE1M2_NO_TRADE")
    if not active_available:
        status="UNAVAILABLE_MISSING_GBPUSD_USDJPY_HISTORY"
    elif {"GBPUSD","USDJPY"}.issubset(available):
        status="READY"
    else:
        status="READY_PARTIAL"
    return positions,status


def _read_cross_asset_ledger():
    if not CROSS_ASSET_LEDGER_PATH.exists():
        return [],"0"*64
    rows=[json.loads(line) for line in CROSS_ASSET_LEDGER_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    previous="0"*64
    for row in rows:
        record_hash=row.get("record_hash")
        payload={key:value for key,value in row.items() if key!="record_hash"}
        if payload.get("previous_hash")!=previous:
            raise RuntimeError("CROSS_ASSET_LEDGER_PREVIOUS_HASH_MISMATCH")
        expected=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if record_hash!=expected:
            raise RuntimeError("CROSS_ASSET_LEDGER_RECORD_HASH_MISMATCH")
        previous=record_hash
    return rows,previous


def append_cross_asset_observations(prediction,actual,resolved_at,code_commit):
    candidate_sets=(
        (CROSS_ASSET_CONTRACT_VERSION,prediction.get("cross_asset_candidates"),prediction.get("cross_asset_status")),
        (CROSS_ASSET_CONTRACT_VERSION_V2,prediction.get("cross_asset_candidates_v2"),prediction.get("cross_asset_status_v2")),
    )
    candidate_sets=[item for item in candidate_sets if isinstance(item[1],dict)]
    if not candidate_sets:
        return 0
    rows,previous=_read_cross_asset_ledger()
    known={row["observation_id"] for row in rows}
    appended=0
    for contract_version,positions,context_status in candidate_sets:
        for candidate_id,position in positions.items():
            if position is None:
                continue
            observation_id=f"{prediction['prediction_id']}::{candidate_id}"
            if observation_id in known:
                continue
            position=int(position)
            gross=position*float(actual)
            friction=FRICTION if position else 0.0
            payload={
                "schema":"claimlab.live_cross_asset_observation.v1",
                "observation_id":observation_id,
                "prediction_id":prediction["prediction_id"],
                "candidate_id":candidate_id,
                "contract_version":contract_version,
                "issued_at":prediction["prediction_ts"],
                "target_at":prediction["target_at"],
                "resolved_at":resolved_at,
                "position":position,
                "actual_return":float(actual),
                "gross_return":gross,
                "friction":friction,
                "net_return":gross-friction,
                "provider":prediction.get("provider","Yahoo"),
                "source_candle_ts":prediction.get("source_candle_ts"),
                "observed_at":prediction.get("observed_at"),
                "data_age_seconds":prediction.get("data_age_seconds"),
                "freshness_status":prediction.get("freshness_status"),
                "context_status":context_status,
                "available_symbols":prediction.get("cross_asset_available_symbols",[]),
                "code_commit":code_commit,
                "previous_hash":previous,
            }
            record_hash=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            payload["record_hash"]=record_hash
            CROSS_ASSET_LEDGER_PATH.parent.mkdir(parents=True,exist_ok=True)
            with CROSS_ASSET_LEDGER_PATH.open("a",encoding="utf-8") as handle:
                handle.write(json.dumps(payload,sort_keys=True)+chr(10))
            rows.append(payload); known.add(observation_id); previous=record_hash; appended+=1
    if appended:
        _read_cross_asset_ledger()
    return appended



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
    """Measure freshness from candle close; feed timestamps label candle opens."""
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
        existing_ids={item.get("prediction_id") for item in ledger._rows()}
        if row["prediction_id"] not in existing_ids:
            ledger.append(Observation(**obs))
        if not ledger.verify():
            raise RuntimeError("LIVE_CLAIM_LEDGER_INTEGRITY_FAILURE")
        if row.get("cross_asset_candidates") and not row.get("cross_asset_observations_written"):
            append_cross_asset_observations(row,actual,resolved_at,code_commit)
            row["cross_asset_observations_written"]=True
        state["bias"]=max(-0.5,min(0.5,0.90*state["bias"]+0.10*error/0.0005))
        hit=((predicted>0 and actual>FRICTION) or (predicted<0 and actual<-FRICTION))
        candidates=[Candidate(x["name"],x["score"],x["predicted_return"]) for x in row.get("algorithms",[])]
        if candidates: update_algorithm_stats(state,candidates,actual)
        state["resolved"]+=1; state["correct"]+=int(hit); state["errors"].append(error); state["errors"]=state["errors"][-500:]
        row.update(actual_return=actual,error=error,hit=hit,resolved_at=resolved_at,status="RESOLVED")
        changed=True
    return changed

EVIDENCE_RELATIVE_PATHS=(
    str(STATE_PATH),str(PRED_PATH),str(CLAIM_LEDGER_PATH),str(CROSS_ASSET_LEDGER_PATH)
)


def _parse_jsonl_text(content):
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _merge_prediction_texts(local_text,remote_text):
    merged={}
    core_keys=("prediction_id","prediction_ts","target_at","prediction",
               "baseline_prediction","source_candle_ts","feature_cutoff_at","config_hash",
               "decision_evidence_sha256")
    for row in _parse_jsonl_text(remote_text)+_parse_jsonl_text(local_text):
        evidence=row.get("decision_evidence")
        if evidence is not None and not verify_decision_evidence(evidence):
            raise RuntimeError(f"LIVE_DECISION_EVIDENCE_HASH_INVALID:{row.get('prediction_id','UNKNOWN')}")
        if evidence is not None and row.get("decision_evidence_sha256") != evidence.get("snapshot_sha256"):
            raise RuntimeError(f"LIVE_DECISION_EVIDENCE_HASH_REFERENCE_MISMATCH:{row.get('prediction_id','UNKNOWN')}")
        pid=row.get("prediction_id")
        if not pid:
            # Preserve legacy rows without modern IDs by exact-content hash.
            # They will be quarantined by the live contract gate, not silently lost.
            digest=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            merged.setdefault(("legacy",digest),row)
            continue
        key_id=("id",pid)
        existing=merged.get(key_id)
        if existing is None:
            merged[key_id]=row
            continue
        for key in core_keys:
            if existing.get(key)!=row.get(key):
                raise RuntimeError(f"LIVE_EVIDENCE_PREDICTION_CONFLICT:{pid}:{key}")
        if existing.get("status")=="RESOLVED" and row.get("status")=="RESOLVED":
            for key in ("actual","target_price","error","error_absolute",
                        "baseline_error_absolute","direction_hit"):
                if existing.get(key) is not None and row.get(key) is not None and existing.get(key)!=row.get(key):
                    raise RuntimeError(f"LIVE_EVIDENCE_RESOLUTION_CONFLICT:{pid}:{key}")
        if existing.get("status")!="RESOLVED" and row.get("status")=="RESOLVED":
            merged[key_id]=row
        elif existing.get("status")==row.get("status"):
            old_key=(bool(existing.get("cross_asset_observations_written")),existing.get("resolved_at",""),existing.get("observed_at",""))
            new_key=(bool(row.get("cross_asset_observations_written")),row.get("resolved_at",""),row.get("observed_at",""))
            if new_key>old_key:
                merged[key_id]=row
    return sorted(merged.values(),key=lambda row:(row.get("prediction_ts",""),row.get("prediction_id",""),json.dumps(row,sort_keys=True)))


def _merge_claim_ledger_texts(local_text,remote_text):
    merged={}
    for row in _parse_jsonl_text(remote_text)+_parse_jsonl_text(local_text):
        body={key:value for key,value in row.items() if key not in ("previous_hash","ledger_hash")}
        observation=Observation(**body)
        pid=observation.prediction_id
        existing=merged.get(pid)
        if existing is None:
            merged[pid]=body
            continue
        for key,value in body.items():
            if key=="resolved_at":
                continue
            if existing.get(key)!=value:
                raise RuntimeError(f"LIVE_EVIDENCE_LEDGER_CONFLICT:{pid}:{key}")
        if body.get("resolved_at","")>existing.get("resolved_at",""):
            merged[pid]=body
    ordered=sorted(merged.values(),key=lambda row:(row["issued_at"],row["prediction_id"]))
    CLAIM_LEDGER_PATH.parent.mkdir(parents=True,exist_ok=True)
    CLAIM_LEDGER_PATH.unlink(missing_ok=True)
    ledger=Ledger(CLAIM_LEDGER_PATH)
    ledger.append_many([Observation(**row) for row in ordered])
    if not ledger.verify():
        raise RuntimeError("LIVE_EVIDENCE_MERGED_CLAIM_LEDGER_INVALID")


def _merge_cross_asset_ledger_texts(local_text,remote_text):
    merged={}
    for row in _parse_jsonl_text(remote_text)+_parse_jsonl_text(local_text):
        body={key:value for key,value in row.items() if key not in ("previous_hash","record_hash")}
        oid=body.get("observation_id")
        if not oid:
            raise RuntimeError("CROSS_ASSET_OBSERVATION_WITHOUT_ID")
        existing=merged.get(oid)
        if existing is None:
            merged[oid]=body
            continue
        for key,value in body.items():
            if key=="resolved_at":
                continue
            if existing.get(key)!=value:
                raise RuntimeError(f"CROSS_ASSET_OBSERVATION_CONFLICT:{oid}:{key}")
        if body.get("resolved_at","")>existing.get("resolved_at",""):
            merged[oid]=body
    ordered=sorted(merged.values(),key=lambda row:(row.get("issued_at",""),row.get("candidate_id",""),row.get("observation_id","")))
    CROSS_ASSET_LEDGER_PATH.parent.mkdir(parents=True,exist_ok=True)
    CROSS_ASSET_LEDGER_PATH.unlink(missing_ok=True)
    previous="0"*64
    with CROSS_ASSET_LEDGER_PATH.open("w",encoding="utf-8") as handle:
        for body in ordered:
            payload=dict(body)
            payload["previous_hash"]=previous
            digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            payload["record_hash"]=digest
            handle.write(json.dumps(payload,sort_keys=True)+chr(10))
            previous=digest
    _read_cross_asset_ledger()


def _merge_concurrent_evidence_to_main():
    local_text={path:(Path(path).read_text(encoding="utf-8") if Path(path).exists() else "") for path in EVIDENCE_RELATIVE_PATHS}
    remote_text={}
    for path in EVIDENCE_RELATIVE_PATHS:
        result=subprocess.run(["git","show",f"origin/main:{path}"],capture_output=True,text=True)
        remote_text[path]=result.stdout if result.returncode==0 else ""
    subprocess.run(["git","reset","--hard","origin/main"],check=True)
    predictions=_merge_prediction_texts(local_text[str(PRED_PATH)],remote_text[str(PRED_PATH)])
    PRED_PATH.parent.mkdir(parents=True,exist_ok=True)
    PRED_PATH.write_text("".join(json.dumps(row,sort_keys=True)+chr(10) for row in predictions),encoding="utf-8")
    _merge_claim_ledger_texts(local_text[str(CLAIM_LEDGER_PATH)],remote_text[str(CLAIM_LEDGER_PATH)])
    _merge_cross_asset_ledger_texts(local_text[str(CROSS_ASSET_LEDGER_PATH)],remote_text[str(CROSS_ASSET_LEDGER_PATH)])
    local_state=json.loads(local_text[str(STATE_PATH)]) if local_text[str(STATE_PATH)].strip() else {}
    remote_state=json.loads(remote_text[str(STATE_PATH)]) if remote_text[str(STATE_PATH)].strip() else {}
    state=max((local_state,remote_state),key=lambda item:item.get("last_cycle_at",""),default={})
    state=dict(state)
    last_predictions=[item.get("last_prediction") for item in (local_state,remote_state) if item.get("last_prediction")]
    if last_predictions:
        state["last_prediction"]=max(last_predictions)
    last_cycles=[item.get("last_cycle_at") for item in (local_state,remote_state) if item.get("last_cycle_at")]
    if last_cycles:
        state["last_cycle_at"]=max(last_cycles)
    state["context_cycles"]=max(local_state.get("context_cycles",0),remote_state.get("context_cycles",0))
    _reconcile_current_contract_metrics(state)
    save_state(state)
    existing=[path for path in EVIDENCE_RELATIVE_PATHS if Path(path).exists()]
    subprocess.run(["git","add","--",*existing],check=True)
    if subprocess.run(["git","diff","--cached","--quiet"]).returncode==0:
        return True
    subprocess.run(["git","commit","-m","chore: reconcile concurrent live evidence [skip ci]"],check=True)
    push=subprocess.run(["git","push","origin","HEAD:main"],capture_output=True,text=True)
    return push.returncode==0


def _push_commit_with_rebase(max_attempts=4):
    """Serialize evidence persistence against concurrent main-branch updates."""
    last_error = ""
    for attempt in range(max_attempts):
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        rebase = subprocess.run(
            ["git", "rebase", "origin/main"], capture_output=True, text=True
        )
        if rebase.returncode != 0:
            conflict_result=subprocess.run(
                ["git","diff","--name-only","--diff-filter=U"],capture_output=True,text=True
            )
            conflict_paths=set(conflict_result.stdout.splitlines())
            subprocess.run(["git", "rebase", "--abort"], check=False)
            if conflict_paths and conflict_paths.issubset(set(EVIDENCE_RELATIVE_PATHS)):
                if _merge_concurrent_evidence_to_main():
                    return
                last_error="LIVE_EVIDENCE_RECONCILE_PUSH_REJECTED"
                continue
            detail = (rebase.stderr or rebase.stdout or "unknown rebase conflict")[-1200:]
            raise RuntimeError(f"LIVE_EVIDENCE_REBASE_CONFLICT: {detail}")
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"], capture_output=True, text=True
        )
        if push.returncode == 0:
            return
        last_error = (push.stderr or push.stdout or "push rejected")[-1200:]
        if attempt + 1 < max_attempts:
            time.sleep(attempt + 1)
    raise RuntimeError(f"LIVE_EVIDENCE_PUSH_RETRIES_EXHAUSTED: {last_error}")


def git_commit():
    if not os.environ.get("GITHUB_ACTIONS"): return
    subprocess.run(["git","config","user.name","github-actions[bot]"],check=False)
    subprocess.run(["git","config","user.email","41898282+users.noreply.github.com"],check=False)
    evidence_paths=[p for p in (STATE_PATH,PRED_PATH,CLAIM_LEDGER_PATH,CROSS_ASSET_LEDGER_PATH) if p.exists()]
    if not evidence_paths:return
    subprocess.run(["git","add",*[str(p) for p in evidence_paths]],check=True)
    if subprocess.run(["git","diff","--cached","--quiet"]).returncode==0:return
    subprocess.run(["git","commit","-m","chore: persist live ClaimLab evidence [skip ci]"],check=True)
    # Fetch/rebase before pushing; other research/maintenance runs may update main.
    # Any conflict or exhausted retry is a real cycle failure, not a silent success.
    _push_commit_with_rebase()

def cycle():
    now=datetime.now(timezone.utc)
    code_commit=os.environ.get("GITHUB_SHA","LOCAL")
    state=load_state()
    predictions=read_predictions()
    pre_changed=False

    # Resolve due forecasts from any closed EURUSD rows before requiring a
    # long contiguous feature window. A feature-data gap must not erase valid
    # target-price evidence for predictions already issued.
    try:
        raw_rows=closed_1m_rows("EURUSD",now)
    except (HTTPError,URLError,TimeoutError,OSError,RuntimeError) as exc:
        raw_rows=[]
        print(f"PENDING_SETTLEMENT_FEED_WARNING: {type(exc).__name__}: {exc}")
    if raw_rows:
        pre_changed=settle(
            predictions,[row[0] for row in raw_rows],[row[1] for row in raw_rows],
            state,code_commit)
        if pre_changed:
            state["last_cycle_at"]=iso(datetime.now(timezone.utc))
            save_predictions(predictions); save_state(state); git_commit()
            state=load_state(); predictions=read_predictions()

    try:
        data,times=aligned_closed_1m_series(now)
        ohlc_map,ohlc_times=aligned_closed_1m_ohlc(now)
        # The two HTTP fetches can straddle a minute boundary. Join only
        # timestamps present in both snapshots; never pair different bars.
        common=sorted(set(times).intersection(ohlc_times))
        if len(common)<30:
            raise RuntimeError(
                f"INSUFFICIENT_COMMON_CLOSE_OHLC_TIMESTAMPS:{len(common)}:"
                f"close_rows={len(times)}:ohlc_rows={len(ohlc_times)}")
    except (RuntimeError,HTTPError,URLError,TimeoutError,OSError) as exc:
        print(
            f"LIVE_CYCLE_HOLD: {type(exc).__name__}: {exc}; "
            "pending_settlement_attempted=true; new_forecast_emitted=false"
        )
        return "HOLD"

    close_index={ts:i for i,ts in enumerate(times)}
    ohlc_index={ts:i for i,ts in enumerate(ohlc_times)}
    data={k:[v[close_index[ts]] for ts in common] for k,v in data.items()}
    ohlc_map={k:[v[ohlc_index[ts]] for ts in common] for k,v in ohlc_map.items()}
    times=ohlc_times=common
    latest_ts=times[-1]
    latest_price=data["EURUSD"][-1]
    source_candle_ts=latest_ts
    observed_at=datetime.now(timezone.utc)
    data_age_seconds=_freshness_age_seconds(source_candle_ts,observed_at)
    if data_age_seconds>90:
        print(
            f"LIVE_CYCLE_HOLD: STALE_EURUSD_FRESHNESS_EVIDENCE:{data_age_seconds:.1f}s; "
            "pending_settlement_attempted=true; new_forecast_emitted=false"
        )
        return "HOLD"

    prices=data["EURUSD"]
    changed=settle(predictions,times,prices,state,code_commit) or pre_changed
    issued=False
    if state.get("last_prediction")!=iso(latest_ts):
        series={k:v[-60:] for k,v in data.items()}
        context=collect_external_context(list(zip(times[-120:],data["EURUSD"][-120:])),now=latest_ts)
        signal,direction,score,predicted_return,candidates,baseline_prediction=predict(
            series,ohlc_map["EURUSD"][-60:],state,context)
        cross_asset_enabled=all(k in series for k in ("GBPUSD","USDJPY","DXY"))
        cross_candidates,cross_status=cross_asset_candidates(series)
        cross_candidates_v2,cross_status_v2=cross_asset_candidates_v2(series)
        config={"engine":f"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+{signal.name}",
                "cross_asset_enabled":cross_asset_enabled,
                "cross_asset_contract":CROSS_ASSET_CONTRACT_VERSION,
                "cross_asset_contract_v2":CROSS_ASSET_CONTRACT_VERSION_V2,
                "horizon_seconds":300,"friction":FRICTION}
        import hashlib
        config_hash=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        issued_at,target_bar_open,target_at=_prediction_times(latest_ts)
        decision_evidence=build_decision_evidence(
            candle_times=times[-60:],
            series=series,
            ohlc={key: values[-60:] for key,values in ohlc_map.items()},
            source_candle_ts=source_candle_ts,
            issued_at=issued_at,
            config_hash=config_hash,
            model_components={
                "signal_name":signal.name,
                "signal_score":float(signal.score),
                "signal_confidence":float(signal.confidence),
                "signal_regime":str(signal.regime),
                "signal_contradiction":bool(signal.contradiction),
                "adjusted_score":float(score),
                "baseline_prediction":float(baseline_prediction),
                "algorithms":[{"name":c.name,"score":float(c.score),"predicted_return":float(c.predicted_return)} for c in candidates],
                "cross_asset_candidates":cross_candidates,
                "cross_asset_candidates_v2":cross_candidates_v2,
            },
            external_context=context,
        )
        row={"prediction_id":f"live-eurusd-1m-{latest_ts.strftime('%Y%m%dT%H%M%SZ')}","prediction_ts":iso(issued_at),
          "target_ts":iso(target_bar_open),"target_at":iso(target_at),
          "data_contract_version":LIVE_DATA_CONTRACT_VERSION,
          "entry_price":latest_price,"direction":direction,"score":score,"confidence":signal.confidence,"regime":signal.regime,"contradiction":signal.contradiction,
          "predicted_return":predicted_return,"baseline_prediction":baseline_prediction,
          "algorithms":[{"name":c.name,"score":c.score,"predicted_return":c.predicted_return} for c in candidates],"external_context":context,
          "decision_evidence":decision_evidence,"decision_evidence_sha256":decision_evidence["snapshot_sha256"],
          "config_hash":config_hash,"status":"PENDING","cross_asset_enabled":cross_asset_enabled,
          "cross_asset_contract_version":CROSS_ASSET_CONTRACT_VERSION,"cross_asset_candidates":cross_candidates,"cross_asset_status":cross_status,
          "cross_asset_available_symbols":sorted(k for k in series if k!="EURUSD"),
          "cross_asset_contract_version_v2":CROSS_ASSET_CONTRACT_VERSION_V2,"cross_asset_candidates_v2":cross_candidates_v2,"cross_asset_status_v2":cross_status_v2,
          "provider":"Yahoo","source_candle_ts":iso(source_candle_ts),"observed_at":iso(observed_at),
          "data_age_seconds":data_age_seconds,"freshness_limit_seconds":90.0,"freshness_status":"FRESH",
          "engine":f"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+{signal.name}+NEWS+TOP50-24H+DATACENTER-POWER+ONLINE-CALIBRATION"}
        predictions.append(row); state["last_prediction"]=iso(latest_ts); state["context_cycles"]=state.get("context_cycles",0)+1; state["last_external_context"]=context; changed=True; issued=True; print(json.dumps(row,sort_keys=True))
    state["last_cycle_at"]=iso(datetime.now(timezone.utc)); state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None
    save_predictions(predictions); save_state(state)
    if changed: git_commit()
    return "FORECAST" if issued else "NO_NEW_FORECAST"

def main():
    cycles=int(os.environ.get("LIVE_CYCLES","5"))
    successful=0
    forecasts=0
    holds=0
    no_new_forecast=0
    failures=[]
    for i in range(cycles):
        try:
            outcome=cycle()
            if outcome=="FORECAST": forecasts+=1
            elif outcome=="HOLD": holds+=1
            else: no_new_forecast+=1
            successful+=1
        except Exception as exc:
            # A stale feed during the known FX weekend closure is an expected
            # no-trade state, not a failed forecasting cycle. Never emit a new
            # forecast from stale prices.
            from engine.market_session import expected_weekend_closure
            reason = f"{type(exc).__name__}: {exc}"
            if expected_weekend_closure(datetime.now(timezone.utc)) and (
                "STALE_EURUSD_FEED" in reason
                or "STALE_EURUSD_FRESHNESS_EVIDENCE" in reason
                or "INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES" in reason
                or "EURUSD_ONE_MINUTE_FEED_UNAVAILABLE" in reason
            ):
                state = load_state()
                state["market_status"] = {
                    "status": "MARKET_CLOSED_EXPECTED",
                    "reason": "WEEKEND_FX_SESSION",
                    "observed_at": iso(datetime.now(timezone.utc)),
                    "last_valid_prediction": state.get("last_prediction"),
                    "new_forecast_emitted": False,
                    "source_error": reason,
                }
                save_state(state)
                print("MARKET_CLOSED_EXPECTED: no new forecast emitted; last valid evidence preserved")
                successful += 1
                holds += 1
            else:
                failures.append(reason)
                print(f"LIVE_CYCLE_ERROR: {reason}")
        if i+1<cycles:
            time.sleep(SLEEP_SECONDS)
    print(f"LIVE_CYCLE_SUMMARY: cycles={cycles} forecasts={forecasts} holds={holds} no_new_forecast={no_new_forecast} errors={len(failures)}")
    if failures:
        raise SystemExit("LIVE_CYCLE_ERRORS: " + " | ".join(failures[-5:]))
    if successful==0:
        raise SystemExit("NO_SUCCESSFUL_LIVE_CYCLES")


if __name__ == "__main__":
    main()
