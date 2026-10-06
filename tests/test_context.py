from datetime import datetime, timezone
from engine.context import trader_leaderboard, fuse_context

def test_trader_leaderboard_selects_lowest_error():
    now=datetime(2026,10,6,12,0,tzinfo=timezone.utc)
    path="tests/fixtures/trader_signals.jsonl"
    out=trader_leaderboard([(datetime(2026,10,6,12,0,tzinfo=timezone.utc),1.0)], path, now)
    assert out["count"] == 2
    assert out["leaders"][0]["trader_id"] == "good"

def test_context_fusion_is_bounded():
    x=fuse_context({"score":1.0,"volume":1.0},{"score":-1.0,"count":50},{"score":1.0,"status":"OK"})
    assert -1 <= x.context_score <= 1
    assert x.trader_count == 50
