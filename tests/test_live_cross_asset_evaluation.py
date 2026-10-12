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


def test_forward_evaluation_excludes_pre_activation_rows(tmp_path, monkeypatch):
    prereg=tmp_path/"registration.json"
    prereg.write_text(json.dumps({
        "candidate_ids":["LIVE1M_NO_TRADE","LIVE1M_DOLLAR_CONSENSUS_3M"],
        "activation_time":"2026-10-12T01:23:59Z"
    }))
    monkeypatch.setattr("scripts.evaluate_live_cross_asset.REGISTRATION",prereg)
    old_row={
        "contract_version":CROSS_ASSET_CONTRACT_VERSION,
        "freshness_status":"FRESH",
        "issued_at":"2026-10-09T10:06:30+00:00",
        "candidate_id":"LIVE1M_DOLLAR_CONSENSUS_3M",
        "position":1,"actual_return":0.0003
    }
    result=evaluate([old_row],code_commit="test")
    assert result["execution"]["rows_in_hash_chain"] == 1
    assert result["execution"]["eligible_fresh_rows"] == 0
    assert result["metrics"]["LIVE1M_DOLLAR_CONSENSUS_3M"]["resolved_observations"] == 0
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_no_trade_control_alone_does_not_kill_unobserved_candidates(tmp_path, monkeypatch):
    prereg=tmp_path/"registration.json"
    prereg.write_text(json.dumps({
        "candidate_ids":["LIVE1M_NO_TRADE","LIVE1M_DOLLAR_CONSENSUS_3M"],
        "activation_time":"2026-10-12T01:23:59Z"
    }))
    monkeypatch.setattr("scripts.evaluate_live_cross_asset.REGISTRATION",prereg)
    rows=[{
        "contract_version":CROSS_ASSET_CONTRACT_VERSION,
        "freshness_status":"FRESH",
        "issued_at":"2026-10-12T01:24:00+00:00",
        "candidate_id":"LIVE1M_NO_TRADE","position":0,"actual_return":0.0
    } for _ in range(1000)]
    result=evaluate(rows,code_commit="test")
    assert result["metrics"]["LIVE1M_NO_TRADE"]["resolved_observations"] == 1000
    assert result["metrics"]["LIVE1M_DOLLAR_CONSENSUS_3M"]["resolved_observations"] == 0
    assert result["verdict"] == "INSUFFICIENT_DATA"


def test_checked_in_forward_preregistration_is_valid_and_locked():
    from pathlib import Path
    prereg=json.loads(Path("research/LIVE_CROSS_ASSET_PREREGISTRATION.json").read_text(encoding="utf-8"))
    assert prereg["activation_time"] == "2026-10-12T01:23:59Z"
    assert prereg["candidate_ids"][0] == "LIVE1M_NO_TRADE"
