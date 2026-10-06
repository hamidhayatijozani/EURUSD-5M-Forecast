from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Optional
import logging,time
from claimlab.ingestion import YahooEURUSD5mClient
from claimlab.live_ledger import AppendOnlyLedger
from claimlab.statistics import StatisticalEngine
logger=logging.getLogger("ClaimLabLiveLoop")
class LiveEvaluationLoop:
 def __init__(self,poll_interval_seconds=300,ledger_path="research/claimlab_live_ledger.jsonl",client=None):
  self.client=client or YahooEURUSD5mClient(); self.poll_interval=int(poll_interval_seconds); self.ledger=AppendOnlyLedger(ledger_path)
 @staticmethod
 def _closed_cutoff(now):
  now=now.astimezone(timezone.utc); floor=now.replace(minute=(now.minute//5)*5,second=0,microsecond=0); return floor-timedelta(minutes=5)
 def step(self,now:Optional[datetime]=None):
  now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); candle=self.client.fetch_latest_eurusd_candle()
  if not candle: return None
  ts=datetime.fromisoformat(candle["timestamp"].replace("Z","+00:00")).astimezone(timezone.utc)
  if ts>self._closed_cutoff(now) or ts.minute%5!=0 or ts.second!=0: return None
  rows=self.ledger.rows()
  if rows and candle["timestamp"]<=rows[-1]["payload"]["timestamp"]: return rows[-1]["payload"]
  previous=float(rows[-1]["payload"]["close"]) if rows else None
  ret=(float(candle["close"])/previous-1.0) if previous and previous>0 else None
  history=[float(r["payload"]["return"]) for r in rows if r["payload"].get("return") is not None]
  if ret is not None: history.append(ret)
  neff=StatisticalEngine.calculate_effective_n(history,5)
  payload={**candle,"source":"YahooEURUSD5mClient","feature_cutoff_at":candle["timestamp"],"return":ret,"n_raw":len(history),"n_eff":neff,"status":"VALID"}
  self.ledger.append(payload); return payload
 def run(self,max_iterations=1):
  for i in range(max_iterations):
   self.step()
   if i+1<max_iterations: time.sleep(self.poll_interval)
