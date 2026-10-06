"""Append-only ClaimLab ledger with duplicate and chain checks."""
from pathlib import Path
import json, hashlib

class Ledger:
    def __init__(self,path="research/claimlab_ledger.jsonl"):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)

    def _rows(self):
        if not self.path.exists(): return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def append(self, observation):
        rows=self._rows()
        if any(x.get("prediction_id")==observation.prediction_id for x in rows):
            raise ValueError("duplicate prediction_id")
        prev=rows[-1].get("ledger_hash","") if rows else ""
        payload=observation.canonical()
        ledger_hash=hashlib.sha256((prev+payload).encode()).hexdigest()
        row=json.loads(payload); row["previous_hash"]=prev; row["ledger_hash"]=ledger_hash
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(row,sort_keys=True)+"\n")
        return ledger_hash

    def verify(self):
        prev=""
        for row in self._rows():
            if row.get("previous_hash","")!=prev: return False
            body={k:v for k,v in row.items() if k not in ("previous_hash","ledger_hash")}
            expected=hashlib.sha256((prev+json.dumps(body,sort_keys=True,separators=(",",":"))).encode()).hexdigest()
            if expected!=row.get("ledger_hash"): return False
            prev=expected
        return True
