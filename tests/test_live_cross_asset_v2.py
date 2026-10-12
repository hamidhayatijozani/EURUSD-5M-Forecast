import json
from pathlib import Path
from scripts.live_minute_loop import CROSS_ASSET_CONTRACT_VERSION_V2, cross_asset_candidates_v2


def test_v2_preregistration_is_valid_and_locked():
    prereg=json.loads(Path("research/LIVE_CROSS_ASSET_PREREGISTRATION_V2.json").read_text(encoding="utf-8"))
    assert prereg["activation_time"] == "2026-10-12T01:50:00Z"
    assert prereg["contract_version"] == CROSS_ASSET_CONTRACT_VERSION_V2
    assert len(prereg["candidate_ids"]) == 7


def test_v2_family_uses_gbpusd_and_usdjpy_without_dxy():
    eurusd=[1.1+i*0.0001 for i in range(40)]
    gbpusd=[1.3+i*0.0002 for i in range(40)]
    usdjpy=[150.0-i*0.01 for i in range(40)]
    positions,status=cross_asset_candidates_v2({"EURUSD":eurusd,"GBPUSD":gbpusd,"USDJPY":usdjpy})
    assert status == "READY"
    assert positions["LIVE1M2_NO_TRADE"] == 0
    assert positions["LIVE1M2_USDJPY_INVERSE_3M"] == 1
    assert positions["LIVE1M2_GBPUSD_MOMENTUM_3M"] == 1
    assert positions["LIVE1M2_GBPUSD_USDJPY_CONSENSUS_3M"] == 1
    assert positions["LIVE1M2_EURUSD_MOMENTUM_CONFIRMED_2SOURCE"] == 1
