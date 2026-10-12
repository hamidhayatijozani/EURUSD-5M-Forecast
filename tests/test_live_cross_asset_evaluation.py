import json
from scripts.evaluate_live_cross_asset import evaluate
from scripts.live_minute_loop import CROSS_ASSET_CONTRACT_VERSION


def test_forward_evaluation_reports_insufficient_data_without_claiming_survival(tmp_path, monkeypatch):
    prereg=tmp_path/"registration.json"
    prereg.write_text(json.dumps({"candidate_ids":["LIVE1M_NO_TRADE","LIVE1M_DOLLAR_CONSENSUS_3M"],"activation_time":"2026-10-12T01:23:59Z"}))
    monkeypatch.setattr("scripts.evaluate_live_cross_asset.REGISTRATION",prereg)
    result=evaluate([],code_commit="test")
    assert result["status"]=="INSUFFICIENT_DATA"
    assert result["verdict"]=="INSUFFICIENT_DATA"
    assert result["surviving_candidates"]==[]
    assert result["metrics"]["LIVE1M_DOLLAR_CONSENSUS_3M"]["status"]=="INSUFFICIENT_DATA"
