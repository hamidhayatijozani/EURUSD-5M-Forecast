from datetime import datetime, timezone, timedelta
from engine.registry import ForecastRecord, record_is_temporally_valid, score_record

def rec():
    now=datetime.now(timezone.utc)
    return ForecastRecord("x", now.isoformat(), (now+timedelta(minutes=1)).isoformat(), (now+timedelta(minutes=6)).isoformat(), "EURUSD","5m","UP",.8,1.1,"baseline-v1","TREND_UP")

def test_temporal_lock(): assert record_is_temporally_valid(rec())
def test_scoring():
    r=rec(); s=score_record(r,1.1011); assert s["correct"] and s["actual_direction"]=="UP"
