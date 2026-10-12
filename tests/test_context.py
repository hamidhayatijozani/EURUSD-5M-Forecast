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


def test_context_fusion_exposes_missing_source_statuses():
    x=fuse_context(
        {"score":0.0,"volume":0.0,"status":"EMPTY"},
        {"score":0.0,"count":0,"status":"NO_SIGNAL_FILE"},
        {"score":0.0,"status":"UNAVAILABLE:NO_API_KEY"},
    )
    assert x.news_status == "EMPTY"
    assert x.trader_status == "NO_SIGNAL_FILE"
    assert x.power_status == "UNAVAILABLE:NO_API_KEY"
    assert x.directional_sources_available == 0
    assert x.context_coverage == 0.0
    assert x.context_degraded is True


def test_trader_leaderboard_reports_missing_signal_file(tmp_path):
    out=trader_leaderboard([],path=str(tmp_path/"missing.jsonl"),
                           now=datetime(2026,10,6,12,0,tzinfo=timezone.utc))
    assert out["count"] == 0
    assert out["status"] == "NO_SIGNAL_FILE"
