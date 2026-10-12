"""Evaluate the separately preregistered GBPUSD/USDJPY forward family."""
import json, os
from pathlib import Path
from scripts.live_minute_loop import _read_cross_asset_ledger, CROSS_ASSET_CONTRACT_VERSION_V2
from scripts.evaluate_live_cross_asset import evaluate

REGISTRATION=Path("research/LIVE_CROSS_ASSET_PREREGISTRATION_V2.json")
OUTPUT=Path("evidence/cross-asset-forward-evaluation-v2.json")


def main():
    rows,_=_read_cross_asset_ledger()
    result=evaluate(
        rows,
        code_commit=os.getenv("GITHUB_SHA","LOCAL"),
        registration_path=REGISTRATION,
        contract_version=CROSS_ASSET_CONTRACT_VERSION_V2,
        no_trade_candidate="LIVE1M2_NO_TRADE",
    )
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
