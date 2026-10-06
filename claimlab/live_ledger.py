import hashlib,json,os
from pathlib import Path
GENESIS="0"*64
class AppendOnlyLedger:
 def __init__(self,path): self.path=Path(path)
 def _read(self):
  if not self.path.exists(): return []
  return [json.loads(x) for x in self.path.read_text(encoding="utf-8").splitlines() if x.strip()]
 @staticmethod
 def _digest(previous_hash,payload):
  s=json.dumps({"previous_hash":previous_hash,"payload":payload},sort_keys=True,separators=(",",":"),ensure_ascii=False)
  return hashlib.sha256(s.encode()).hexdigest()
 def append(self,payload):
  rows=self._read(); prev=rows[-1]["hash"] if rows else GENESIS
  if rows and payload.get("timestamp","")<=rows[-1]["payload"].get("timestamp",""): raise ValueError("LEDGER_TIMESTAMP_NOT_MONOTONIC")
  entry={"index":len(rows),"previous_hash":prev,"payload":payload}
  entry["hash"]=self._digest(prev,payload)
  self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.path.open("a",encoding="utf-8") as f:
   f.write(json.dumps(entry,sort_keys=True,ensure_ascii=False)+"\n"); f.flush(); os.fsync(f.fileno())
  return entry
 def verify(self):
  prev=GENESIS
  for i,row in enumerate(self._read()):
   if row.get("index")!=i or row.get("previous_hash")!=prev or row.get("hash")!=self._digest(prev,row["payload"]): return False
   prev=row["hash"]
  return True
 def rows(self): return self._read()
