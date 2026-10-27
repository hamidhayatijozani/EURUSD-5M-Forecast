"""Every-minute real-market 5-minute forecasting with exact-target resolution and ClaimLab evidence."""
import hashlib, json, os, subprocess, time, sqlite3, tempfile
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from pathlib import Path
from statistics import pstdev
from engine.algorithm_factory import adaptive_ensemble, update_algorithm_stats, Candidate
from engine.experiments import combined, pst_signal
from engine.context import collect_external_context
from engine.forecast import forecast
from engine.live_feed import aligned_closed_1m_series, aligned_closed_1m_ohlc, closed_1m_rows
from engine.market_providers import LAST_PROVIDER_BY_SYMBOL
from claimlab.ledger import Ledger
from claimlab.registry import registry_hash
from claimlab.resolver import resolve
from claimlab.schema import Observation
from engine.forecast_evidence import build_decision_evidence, verify_decision_evidence
from claimlab.live_evidence_bridge import (persist_issue, persist_settlement, audit_stores, has_verified_issuance, EVIDENCE_JSONL, SETTLEMENTS_JSONL, SQLITE_PATH)
from claimlab.evidence_store import JsonLedger, LedgerDB, canonical_json
from claimlab.live_provenance import require_freshness_provenance

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
    # FLAT is a no-trade decision. Keep the numeric prediction consistent so
    # ClaimLab settlement cannot turn a FLAT label into a directional position.
    predicted_return=adjusted*0.0005 if direction != "FLAT" else 0.0
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
        if row.get("resolved_at") or str(row.get("status", "")).startswith("EXCLUDED_"):
            continue
        # A rollout can leave a pending prediction in the legacy prediction file
        # without its immutable bridge issuance. Do not fabricate an issuance or
        # let that orphan block every subsequent forecast cycle: quarantine it.
        if row.get("decision_evidence") and not has_verified_issuance(
            row.get("prediction_id"), evidence_dir=PRED_PATH.parent
        ):
            row.update(
                status="EXCLUDED_MISSING_ISSUANCE",
                excluded_reason="No matching issuance in verified live evidence ledger; settlement prohibited",
            )
            changed=True
            print(f"LIVE_PENDING_QUARANTINED_MISSING_ISSUANCE:{row.get('prediction_id')}")
            continue
        target=row["target_ts"]  # candle-open key for price lookup
        if target not in price_map: continue
        actual=price_map[target]/float(row["entry_price"])-1.0
        predicted=float(row["predicted_return"]); baseline=float(row["baseline_prediction"])
        error=actual-predicted
        target_dt=datetime.fromisoformat(target.replace("Z","+00:00"))
        resolved_at=iso(target_dt+timedelta(minutes=1))
        if row.get("target_at") != resolved_at:
            raise RuntimeError("LIVE_TARGET_CLOSE_TIMESTAMP_MISMATCH")
        provenance=require_freshness_provenance(row)
        obs=resolve({
          "schema_version":"claimlab.observation.v1","prediction_id":row["prediction_id"],
          "issued_at":row["prediction_ts"],"target_at":row["target_at"],
          "feature_cutoff_at":row.get("decision_evidence",{}).get("feature_cutoff_at",row["prediction_ts"]),
          "symbol":"EURUSD","horizon_seconds":HORIZON*60,"prediction":predicted,"code_commit":code_commit,
          "config_hash": row["config_hash"],
          "claim_registry_hash": registry_hash(),
          **provenance},
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
        if row.get("decision_evidence"):
            persist_settlement(row, actual, resolved_at, evidence_dir=PRED_PATH.parent)
        row.update(actual_return=actual,error=error,hit=hit,resolved_at=resolved_at,status="RESOLVED")
        changed=True
    return changed

# Keep the four legacy text ledgers on their existing merge path. The
# bridge JSONL and SQLite stores are reconciled together as one unit below.
EVIDENCE_TEXT_RELATIVE_PATHS=(
    str(STATE_PATH),str(PRED_PATH),str(CLAIM_LEDGER_PATH),str(CROSS_ASSET_LEDGER_PATH)
)
LIVE_BRIDGE_TEXT_PATHS=(str(EVIDENCE_JSONL),str(SETTLEMENTS_JSONL))
EVIDENCE_RELATIVE_PATHS=EVIDENCE_TEXT_RELATIVE_PATHS+LIVE_BRIDGE_TEXT_PATHS+(str(SQLITE_PATH),)


def _parse_jsonl_text(content):
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _merge_prediction_texts(local_text,remote_text):
    merged={}
    core_keys=("prediction_id","prediction_ts","target_at","prediction",
               "baseline_prediction","source_candle_ts","feature_cutoff_at","config_hash")
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


def _parse_utc_timestamp(value):
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise RuntimeError("LIVE_BRIDGE_TIMESTAMP_MISSING_TIMEZONE")
    return parsed.astimezone(timezone.utc)


def _read_live_bridge_db_snapshot(db_path):
    """Read bridge SQLite as a validated snapshot without mutating its source."""
    path=Path(db_path)
    empty={"predictions":{},"snapshots":{},"settlements":{}}
    if not path.exists() or path.stat().st_size==0:
        return empty
    connection=None
    try:
        connection=sqlite3.connect(str(path))
        connection.row_factory=sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        tables={row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        required={"predictions","snapshots","settlements"}
        if not required.issubset(tables):
            if not tables:
                return empty
            raise RuntimeError("LIVE_BRIDGE_SQLITE_SCHEMA_INCOMPLETE")
        snapshot={
            "predictions":{},
            "snapshots":{},
            "settlements":{},
        }
        for row in connection.execute(
            "SELECT prediction_id,evidence_hash,payload_json FROM predictions"
        ).fetchall():
            pid=row["prediction_id"]
            if pid in snapshot["predictions"]:
                raise RuntimeError(f"LIVE_BRIDGE_SQLITE_DUPLICATE_PREDICTION:{pid}")
            snapshot["predictions"][pid]={
                "evidence_hash":row["evidence_hash"],
                "payload":json.loads(row["payload_json"]),
            }
        for row in connection.execute(
            "SELECT prediction_id,snapshot_sha256,payload_json FROM snapshots"
        ).fetchall():
            pid=row["prediction_id"]
            if pid in snapshot["snapshots"]:
                raise RuntimeError(f"LIVE_BRIDGE_SQLITE_DUPLICATE_SNAPSHOT:{pid}")
            snapshot["snapshots"][pid]={
                "snapshot_sha256":row["snapshot_sha256"],
                "payload":json.loads(row["payload_json"]),
            }
        for row in connection.execute(
            "SELECT prediction_id,settled_at,payload_json FROM settlements"
        ).fetchall():
            pid=row["prediction_id"]
            if pid in snapshot["settlements"]:
                raise RuntimeError(f"LIVE_BRIDGE_SQLITE_DUPLICATE_SETTLEMENT:{pid}")
            snapshot["settlements"][pid]={
                "settled_at":row["settled_at"],
                "payload":json.loads(row["payload_json"]),
            }
        return snapshot
    except (sqlite3.DatabaseError,json.JSONDecodeError) as exc:
        raise RuntimeError(f"LIVE_BRIDGE_SQLITE_READ_INVALID:{path.name}:{type(exc).__name__}") from exc
    finally:
        if connection is not None:
            connection.close()


def _read_remote_live_bridge_db_snapshot(db_path):
    """Read the remote branch's binary SQLite blob before resetting the worktree."""
    result=subprocess.run(
        ["git","show",f"origin/main:{db_path}"],
        capture_output=True,
    )
    if result.returncode!=0:
        stderr=result.stderr.decode("utf-8",errors="replace")
        if "does not exist" in stderr or "exists on disk, but not in" in stderr:
            return {"predictions":{},"snapshots":{},"settlements":{}}
        raise RuntimeError(f"LIVE_BRIDGE_REMOTE_SQLITE_READ_FAILED:{stderr[-500:]}")
    with tempfile.TemporaryDirectory(prefix="live-bridge-remote-") as directory:
        remote_path=Path(directory)/Path(db_path).name
        remote_path.write_bytes(result.stdout)
        return _read_live_bridge_db_snapshot(remote_path)


def _validate_live_bridge_source(evidence_text,settlement_text,db_snapshot,label):
    """Validate one side independently before unioning concurrent evidence."""
    evidence_rows=_parse_jsonl_text(evidence_text)
    settlement_rows=_parse_jsonl_text(settlement_text)
    with tempfile.TemporaryDirectory(prefix="live-bridge-ledger-") as directory:
        path=Path(directory)/"live_decision_evidence.jsonl"
        path.write_text(evidence_text,encoding="utf-8")
        if not JsonLedger(path).verify():
            raise RuntimeError(f"LIVE_BRIDGE_{label}_JSONL_CHAIN_INVALID")
    evidence_by_id={}
    for raw in evidence_rows:
        pid=raw.get("prediction_id")
        if not pid or pid in evidence_by_id:
            raise RuntimeError(f"LIVE_BRIDGE_{label}_DUPLICATE_OR_MISSING_PREDICTION_ID")
        record={key:value for key,value in raw.items() if key not in ("previous_hash","ledger_hash")}
        evidence_by_id[pid]=record
    prediction_ids=set(evidence_by_id)
    if prediction_ids!=set(db_snapshot["predictions"]):
        raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_PREDICTION_ID_PARITY_FAILURE")
    if prediction_ids!=set(db_snapshot["snapshots"]):
        raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SNAPSHOT_ID_PARITY_FAILURE")
    for pid,record in evidence_by_id.items():
        db_prediction=db_snapshot["predictions"][pid]
        if record.get("evidence_hash")!=db_prediction["evidence_hash"]:
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_EVIDENCE_HASH_MISMATCH:{pid}")
        if canonical_json(record)!=canonical_json(db_prediction["payload"]):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_PREDICTION_PAYLOAD_MISMATCH:{pid}")
        snapshot=record.get("decision_snapshot")
        db_snapshot_row=db_snapshot["snapshots"][pid]
        if not isinstance(snapshot,dict):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SNAPSHOT_MISSING:{pid}")
        if record.get("snapshot_sha256")!=snapshot.get("snapshot_sha256"):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SNAPSHOT_REFERENCE_MISMATCH:{pid}")
        if db_snapshot_row["snapshot_sha256"]!=snapshot.get("snapshot_sha256"):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SNAPSHOT_HASH_MISMATCH:{pid}")
        if canonical_json(db_snapshot_row["payload"])!=canonical_json(snapshot):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SNAPSHOT_PAYLOAD_MISMATCH:{pid}")

    settlement_by_id={}
    for row in settlement_rows:
        pid=row.get("prediction_id")
        if not pid or pid in settlement_by_id:
            raise RuntimeError(f"LIVE_BRIDGE_{label}_DUPLICATE_OR_MISSING_SETTLEMENT_ID")
        settlement_by_id[pid]=row
    if set(settlement_by_id)!=set(db_snapshot["settlements"]):
        raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SETTLEMENT_ID_PARITY_FAILURE")
    for pid,row in settlement_by_id.items():
        if pid not in evidence_by_id:
            raise RuntimeError(f"LIVE_BRIDGE_{label}_ORPHAN_SETTLEMENT:{pid}")
        db_settlement=db_snapshot["settlements"][pid]
        if canonical_json(row)!=canonical_json(db_settlement["payload"]):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SETTLEMENT_PAYLOAD_MISMATCH:{pid}")
        settled_at=row.get("settled_at")
        target_at=row.get("target_at")
        if not settled_at or not target_at:
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SETTLEMENT_TIME_MISSING:{pid}")
        if _parse_utc_timestamp(settled_at)<_parse_utc_timestamp(target_at):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SETTLEMENT_BEFORE_TARGET:{pid}")
        if _parse_utc_timestamp(db_settlement["settled_at"])!=_parse_utc_timestamp(settled_at):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SQLITE_SETTLED_AT_MISMATCH:{pid}")
        if row.get("decision_evidence_sha256")!=evidence_by_id[pid].get("snapshot_sha256"):
            raise RuntimeError(f"LIVE_BRIDGE_{label}_SETTLEMENT_SNAPSHOT_REFERENCE_MISMATCH:{pid}")
    return {
        "predictions":list(evidence_by_id.values()),
        "settlements":list(settlement_by_id.values()),
    }


def _merge_live_bridge_prediction_records(local_records,remote_records):
    merged={}
    for record in list(remote_records)+list(local_records):
        pid=record.get("prediction_id")
        if not pid:
            raise RuntimeError("LIVE_BRIDGE_PREDICTION_ID_REQUIRED")
        existing=merged.get(pid)
        if existing is not None and canonical_json(existing)!=canonical_json(record):
            raise RuntimeError(f"LIVE_BRIDGE_IMMUTABLE_PREDICTION_CONFLICT:{pid}")
        merged[pid]=record
    return sorted(merged.values(),key=lambda row:(row.get("issued_at",""),row.get("prediction_id","")))


def _merge_live_bridge_settlement_records(local_records,remote_records):
    merged={}
    for record in list(remote_records)+list(local_records):
        pid=record.get("prediction_id")
        if not pid:
            raise RuntimeError("LIVE_BRIDGE_SETTLEMENT_ID_REQUIRED")
        existing=merged.get(pid)
        if existing is not None and canonical_json(existing)!=canonical_json(record):
            raise RuntimeError(f"LIVE_BRIDGE_IMMUTABLE_SETTLEMENT_CONFLICT:{pid}")
        merged[pid]=record
    return sorted(merged.values(),key=lambda row:(row.get("settled_at",""),row.get("prediction_id","")))


def _write_live_bridge_store(prediction_records,settlement_records,*,evidence_path=None,settlement_path=None,sqlite_path=None):
    """Rebuild JSONL hash chain and SQLite atomically from validated immutable records."""
    evidence_path=Path(evidence_path or EVIDENCE_JSONL)
    settlement_path=Path(settlement_path or SETTLEMENTS_JSONL)
    sqlite_path=Path(sqlite_path or SQLITE_PATH)
    evidence_path.parent.mkdir(parents=True,exist_ok=True)
    settlement_path.parent.mkdir(parents=True,exist_ok=True)
    sqlite_path.parent.mkdir(parents=True,exist_ok=True)
    evidence_path.unlink(missing_ok=True)
    ledger=JsonLedger(evidence_path)
    ordered_predictions=sorted(prediction_records,key=lambda row:(row.get("issued_at",""),row.get("prediction_id","")))
    for record in ordered_predictions:
        normalized={key:value for key,value in record.items() if key not in ("previous_hash","ledger_hash")}
        ledger.append(normalized)
    if not ledger.verify():
        raise RuntimeError("LIVE_BRIDGE_REBUILT_JSONL_CHAIN_INVALID")
    ordered_settlements=sorted(settlement_records,key=lambda row:(row.get("settled_at",""),row.get("prediction_id","")))
    settlement_path.write_text(
        "".join(canonical_json(row)+"\n" for row in ordered_settlements),
        encoding="utf-8",
    )
    sqlite_path.unlink(missing_ok=True)
    db=LedgerDB(sqlite_path)
    try:
        for record in ordered_predictions:
            normalized={key:value for key,value in record.items() if key not in ("previous_hash","ledger_hash")}
            db.insert_prediction(normalized)
            db.insert_snapshot(normalized["prediction_id"],normalized["decision_snapshot"])
        for settlement in ordered_settlements:
            db.insert_settlement(
                settlement["prediction_id"],
                settlement,
                settled_at=settlement["settled_at"],
            )
    finally:
        db.close()
    if evidence_path.name!="live_decision_evidence.jsonl" or settlement_path.name!="live_decision_settlements.jsonl" or sqlite_path.name!="live_evidence.db":
        raise RuntimeError("LIVE_BRIDGE_AUDIT_REQUIRES_CANONICAL_FILENAMES")
    audit=audit_stores(evidence_dir=evidence_path.parent)
    expected={"status":"AUDITED","predictions":len(ordered_predictions),"snapshots":len(ordered_predictions),"settlements":len(ordered_settlements)}
    if audit!=expected:
        raise RuntimeError(f"LIVE_BRIDGE_REBUILT_STORE_AUDIT_MISMATCH:{audit}")
    return audit


def _git_show_text_or_empty(path):
    result=subprocess.run(["git","show",f"origin/main:{path}"],capture_output=True,text=True)
    if result.returncode==0:
        return result.stdout
    if "does not exist" in (result.stderr or ""):
        return ""
    raise RuntimeError(f"LIVE_EVIDENCE_REMOTE_TEXT_READ_FAILED:{path}:{(result.stderr or '')[-400:]}")


def _merge_concurrent_evidence_to_main():
    # Capture and validate both bridge stores before reset --hard destroys local data.
    local_evidence_text=Path(EVIDENCE_JSONL).read_text(encoding="utf-8") if Path(EVIDENCE_JSONL).exists() else ""
    local_settlement_text=Path(SETTLEMENTS_JSONL).read_text(encoding="utf-8") if Path(SETTLEMENTS_JSONL).exists() else ""
    local_db_snapshot=_read_live_bridge_db_snapshot(SQLITE_PATH)
    local_bridge=_validate_live_bridge_source(
        local_evidence_text,local_settlement_text,local_db_snapshot,"LOCAL"
    )
    remote_evidence_text=_git_show_text_or_empty(str(EVIDENCE_JSONL))
    remote_settlement_text=_git_show_text_or_empty(str(SETTLEMENTS_JSONL))
    remote_db_snapshot=_read_remote_live_bridge_db_snapshot(str(SQLITE_PATH))
    remote_bridge=_validate_live_bridge_source(
        remote_evidence_text,remote_settlement_text,remote_db_snapshot,"REMOTE"
    )
    merged_predictions=_merge_live_bridge_prediction_records(
        local_bridge["predictions"],remote_bridge["predictions"]
    )
    merged_settlements=_merge_live_bridge_settlement_records(
        local_bridge["settlements"],remote_bridge["settlements"]
    )

    # Existing non-bridge evidence ledgers have their own domain-specific merge.
    local_text={path:(Path(path).read_text(encoding="utf-8") if Path(path).exists() else "") for path in EVIDENCE_TEXT_RELATIVE_PATHS}
    remote_text={path:_git_show_text_or_empty(path) for path in EVIDENCE_TEXT_RELATIVE_PATHS}
    subprocess.run(["git","reset","--hard","origin/main"],check=True)
    predictions=_merge_prediction_texts(local_text[str(PRED_PATH)],remote_text[str(PRED_PATH)])
    PRED_PATH.parent.mkdir(parents=True,exist_ok=True)
    PRED_PATH.write_text("".join(json.dumps(row,sort_keys=True)+chr(10) for row in predictions),encoding="utf-8")
    _merge_claim_ledger_texts(local_text[str(CLAIM_LEDGER_PATH)],remote_text[str(CLAIM_LEDGER_PATH)])
    _merge_cross_asset_ledger_texts(local_text[str(CROSS_ASSET_LEDGER_PATH)],remote_text[str(CROSS_ASSET_LEDGER_PATH)])
    _write_live_bridge_store(merged_predictions,merged_settlements)
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
    evidence_paths=[p for p in (STATE_PATH,PRED_PATH,CLAIM_LEDGER_PATH,CROSS_ASSET_LEDGER_PATH,EVIDENCE_JSONL,SETTLEMENTS_JSONL,SQLITE_PATH) if p.exists()]
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
            ohlc={key: values[-60:] for key, values in ohlc_map.items()},
            source_candle_ts=source_candle_ts,
            feature_cutoff_at=source_candle_ts,
            issued_at=issued_at,
            target_ts=target_at,
            config_hash=config_hash,
            model_components={
                "signal_name":signal.name,
                "signal_score":float(signal.score),
                "signal_confidence":float(signal.confidence),
                "signal_regime":str(signal.regime),
                "signal_contradiction":bool(signal.contradiction),
                "adjusted_score":float(score),
                "baseline_prediction":float(baseline_prediction),
                "algorithms":[{"name":item.name,"score":float(item.score),"predicted_return":float(item.predicted_return)} for item in candidates],
                "cross_asset_candidates":cross_candidates,
                "cross_asset_candidates_v2":cross_candidates_v2,
            },
            external_context=context,
        )
        row={"prediction_id":f"live-eurusd-1m-{latest_ts.strftime('%Y%m%dT%H%M%SZ')}","prediction_ts":iso(issued_at),
          "target_ts":iso(target_bar_open),"target_at":iso(target_at),
          "feature_cutoff_at":iso(source_candle_ts),
          "decision_evidence":decision_evidence,"decision_evidence_sha256":decision_evidence["snapshot_sha256"],
          "data_contract_version":LIVE_DATA_CONTRACT_VERSION,
          "entry_price":latest_price,"direction":direction,"score":score,"confidence":signal.confidence,"regime":signal.regime,"contradiction":signal.contradiction,
          "predicted_return":predicted_return,"baseline_prediction":baseline_prediction,
          "algorithms":[{"name":c.name,"score":c.score,"predicted_return":c.predicted_return} for c in candidates],"external_context":context,
          "config_hash":config_hash,"status":"PENDING","cross_asset_enabled":cross_asset_enabled,
          "cross_asset_contract_version":CROSS_ASSET_CONTRACT_VERSION,"cross_asset_candidates":cross_candidates,"cross_asset_status":cross_status,
          "cross_asset_available_symbols":sorted(k for k in series if k!="EURUSD"),
          "cross_asset_contract_version_v2":CROSS_ASSET_CONTRACT_VERSION_V2,"cross_asset_candidates_v2":cross_candidates_v2,"cross_asset_status_v2":cross_status_v2,
          "provider":LAST_PROVIDER_BY_SYMBOL.get("EURUSD","unknown"),"provider_by_symbol":dict(LAST_PROVIDER_BY_SYMBOL),"source_candle_ts":iso(source_candle_ts),"observed_at":iso(observed_at),
          "data_age_seconds":data_age_seconds,"freshness_limit_seconds":90.0,"freshness_status":"FRESH",
          "engine":f"DEEP-OHLC-PATTERNS+ALGORITHM-FACTORY+{signal.name}+NEWS+TOP50-24H+DATACENTER-POWER+ONLINE-CALIBRATION"}
        persist_issue(row, code_commit, evidence_dir=PRED_PATH.parent)
        predictions.append(row); state["last_prediction"]=iso(latest_ts); state["context_cycles"]=state.get("context_cycles",0)+1; state["last_external_context"]=context; changed=True; issued=True; print(json.dumps(row,sort_keys=True))
    state["last_cycle_at"]=iso(datetime.now(timezone.utc)); state["accuracy"]=state["correct"]/state["resolved"] if state["resolved"] else None
    save_predictions(predictions); save_state(state)
    print("LIVE_EVIDENCE_AUDIT:"+json.dumps(audit_stores(evidence_dir=PRED_PATH.parent),sort_keys=True))
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
