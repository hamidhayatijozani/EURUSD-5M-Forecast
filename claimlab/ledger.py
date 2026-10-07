"""Append-only ClaimLab ledger with duplicate and chain checks."""
from pathlib import Path
import json, hashlib


class Ledger:
    def __init__(self, path="research/claimlab_ledger.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self):
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def append(self, observation):
        # Idempotent retry: if a prior process appended but failed before
        # persisting live state, accept the identical observation once.
        for row in self._rows():
            if row.get("prediction_id") != observation.prediction_id:
                continue
            body={key:value for key,value in row.items()
                  if key not in ("previous_hash","ledger_hash")}
            existing_payload=json.dumps(body,sort_keys=True,separators=(",",":"))
            if existing_payload != observation.canonical():
                raise ValueError("conflicting duplicate prediction_id")
            if not self.verify():
                raise RuntimeError("CLAIM_LEDGER_INTEGRITY_FAILURE")
            return row.get("ledger_hash")
        return self.append_many([observation])[0]

    def append_many(self, observations):
        """Append a batch in linear time instead of rereading the ledger per row."""
        batch = list(observations)
        if not batch:
            return []
        rows = self._rows()
        seen = {row.get("prediction_id") for row in rows}
        incoming = [observation.prediction_id for observation in batch]
        if len(set(incoming)) != len(incoming) or any(pid in seen for pid in incoming):
            raise ValueError("duplicate prediction_id")

        previous = rows[-1].get("ledger_hash", "") if rows else ""
        digests = []
        with self.path.open("a", encoding="utf-8") as handle:
            for observation in batch:
                payload = observation.canonical()
                digest = hashlib.sha256((previous + payload).encode()).hexdigest()
                row = json.loads(payload)
                row["previous_hash"] = previous
                row["ledger_hash"] = digest
                handle.write(json.dumps(row, sort_keys=True) + "\n")
                digests.append(digest)
                previous = digest
        return digests

    def verify(self):
        previous = ""
        for row in self._rows():
            if row.get("previous_hash", "") != previous:
                return False
            body = {
                key: value for key, value in row.items()
                if key not in ("previous_hash", "ledger_hash")
            }
            expected = hashlib.sha256(
                (previous + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()
            ).hexdigest()
            if expected != row.get("ledger_hash"):
                return False
            previous = expected
        return True
