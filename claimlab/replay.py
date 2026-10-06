"""Offline, deterministic verification and replay of ClaimLab evidence."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, List
from claimlab.evidence_capsule import EvidenceCapsuleGenerator
from claimlab.live_ledger import AppendOnlyLedger
from claimlab.registry import assert_locked

class LedgerReplayEngine:
    def __init__(self, ledger_path: str, registry_lock_path: str = "claimlab/registry.lock"):
        self.ledger_path = Path(ledger_path)
        self.registry_lock_path = Path(registry_lock_path)

    def verify_ledger_integrity(self) -> bool:
        if not self.ledger_path.exists():
            return False
        return AppendOnlyLedger(self.ledger_path).verify()

    def _records(self) -> List[Dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        return [
            json.loads(line) for line in self.ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def replay_claim(self, claim_id: str) -> Dict[str, Any]:
        if not self.verify_ledger_integrity():
            return {"CLAIM": claim_id, "LEDGER_INTEGRITY": "FAIL", "STATUS": "BLOCKED"}

        try:
            registry_hash = assert_locked()
        except Exception as exc:
            return {
                "CLAIM": claim_id, "LEDGER_INTEGRITY": "VERIFIED",
                "REGISTRY": "FAIL", "STATUS": "BLOCKED", "ERROR": str(exc)
            }

        records = self._records()
        if not records:
            return {
                "CLAIM": claim_id, "LEDGER_INTEGRITY": "VERIFIED",
                "REGISTRY": registry_hash, "STATUS": "INSUFFICIENT_DATA"
            }

        previous_candle = None
        for row in records:
            payload = row["payload"]
            if not EvidenceCapsuleGenerator.verify_temporal_integrity(
                payload["timestamp"], payload["feature_cutoff_at"]
            ):
                return {"CLAIM": claim_id, "LEDGER_INTEGRITY": "VERIFIED",
                        "TEMPORAL_INTEGRITY": "FAIL", "STATUS": "BLOCKED"}
            if previous_candle is not None and payload["timestamp"] <= previous_candle:
                return {"CLAIM": claim_id, "LEDGER_INTEGRITY": "VERIFIED",
                        "TEMPORAL_INTEGRITY": "FAIL", "STATUS": "BLOCKED"}
            previous_candle = payload["timestamp"]

        latest = records[-1]["payload"]
        return {
            "CLAIM": claim_id,
            "DATA_THROUGH": latest.get("candle_timestamp", latest.get("timestamp")),
            "N_RAW": latest.get("n_raw", 0),
            "N_EFF": latest.get("n_eff", 0.0),
            "REGISTRY": latest.get("registry_version", registry_hash),
            "COMMIT": latest.get("code_commit"),
            "LEDGER": "VERIFIED",
            "TEMPORAL_INTEGRITY": "VERIFIED",
            "STATUS": latest.get("claim_state", "INSUFFICIENT_DATA"),
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClaimLab Ledger Replay Utility")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--claim", required=True)
    parser.add_argument("--lock", default="claimlab/registry.lock")
    args = parser.parse_args()
    print(json.dumps(LedgerReplayEngine(args.ledger, args.lock).replay_claim(args.claim),
                     indent=2, sort_keys=True))
