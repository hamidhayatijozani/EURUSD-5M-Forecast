from engine.registry import ForecastRecord,record_is_temporally_valid,score_record

def rec(created="2026-10-04T18:00:00Z",start="2026-10-04T18:05:00Z"):
    return ForecastRecord("x",created,start,"2026-10-04T18:10:00Z","EURUSD","5m","UP",.8,1.1700,"baseline-v1","TREND_UP")

def test_temporal_lock():
    assert record_is_temporally_valid(rec())
    assert not record_is_temporally_valid(rec(created="2026-10-04T18:06:00Z"))

def test_score():
    s=score_record(rec(),1.1710)
    assert s["actual"]=="UP"
    assert s["correct"] is True
