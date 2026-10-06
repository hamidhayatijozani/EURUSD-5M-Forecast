"""Run the real historical EUR/USD walk-forward and emit replay evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from claimlab.ledger import Ledger
from claimlab.schema import Observation
from claimlab.walkforward import DATASET_URL, build_capsule, parse_csv, walk_forward


def main() -> None:
    response = requests.get(DATASET_URL, timeout=60)
    response.raise_for_status()
    text = response.text
    rows = parse_csv(text)
    if len(rows) < 102:
        raise SystemExit("HISTORICAL_DATA_TOO_SHORT")

    code_commit = os.getenv("GITHUB_SHA", "LOCAL")
    observations, config = walk_forward(rows, code_commit=code_commit)

    out_dir = Path("evidence/claimlab-walkforward")
    out_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = out_dir / "observations.jsonl"
    ledger = Ledger(ledger_path)
    for observation in observations:
        ledger.append(observation)

    capsule = build_capsule(
        observations,
        dataset_text=text,
        dataset_ref="main",
        code_commit=code_commit,
        config=config,
    )
    capsule["statistics"]["ledger_integrity"] = 1.0 if ledger.verify() else 0.0
    capsule["verdict"] = __import__("claimlab.verdict", fromlist=["verdict"]).verdict(
        capsule["statistics"]
    )

    (out_dir / "evidence_capsule.json").write_text(
        json.dumps(capsule, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(capsule, sort_keys=True))
    if capsule["verdict"] == "INSUFFICIENT_DATA":
        raise SystemExit("CLAIMLAB_WALKFORWARD_INSUFFICIENT_DATA")


if __name__ == "__main__":
    main()
