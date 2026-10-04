"""Forecast lifecycle with an explicit temporal boundary."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path

@dataclass(frozen=True)
class ForecastRecord:
    forecast_id: str
    created_at: str
    target_start: str
    target_end: str
    instrument: str
    timeframe: str
    direction: str
    confidence: float
    reference_price: float
    model_version: str
    regime: str

def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)

def record_is_temporally_valid(r: ForecastRecord) -> bool:
    return _dt(r.created_at) <= _dt(r.target_start) < _dt(r.target_end)

def score_record(r: ForecastRecord, target_close: float) -> dict:
    if not record_is_temporally_valid(r):
        raise ValueError("forecast creation time must be before target window")
    ret=(target_close-r.reference_price)/r.reference_price
    actual="UP" if ret>0.00005 else "DOWN" if ret<-0.00005 else "FLAT"
    return {**asdict(r),"actual":actual,"return":ret,"correct":actual==r.direction,"scored_at":datetime.now(timezone.utc).isoformat()}

def append_jsonl(path: str | Path, record: dict) -> None:
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("a",encoding="utf-8") as f:
        f.write(json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n")
