from datetime import datetime,timezone
from claimlab.live_ledger import AppendOnlyLedger
from claimlab.live_loop import LiveEvaluationLoop
def test_ledger_hash_chain_and_monotonic_append(tmp_path):
 l=AppendOnlyLedger(tmp_path/"ledger.jsonl"); l.append({"timestamp":"2026-10-06T10:00:00+00:00","close":1.17}); l.append({"timestamp":"2026-10-06T10:05:00+00:00","close":1.18})
 assert l.verify(); assert l.rows()[1]["previous_hash"]==l.rows()[0]["hash"]
 try: l.append({"timestamp":"2026-10-06T10:05:00+00:00","close":1.19})
 except ValueError as e: assert str(e)=="LEDGER_TIMESTAMP_NOT_MONOTONIC"
 else: raise AssertionError("duplicate timestamp accepted")
def test_live_loop_rejects_unclosed_candle(tmp_path):
 class C:
  def fetch_latest_eurusd_candle(self, **kwargs): return {"symbol":"EURUSD","timestamp":"2026-10-06T10:10:00+00:00","open":1.17,"high":1.18,"low":1.16,"close":1.175,"volume":0}
 l=LiveEvaluationLoop(ledger_path=tmp_path/"l.jsonl",client=C())
 assert l.step(datetime(2026,10,6,10,12,tzinfo=timezone.utc)) is None
def test_live_loop_records_closed_candle(tmp_path):
 class C:
  def fetch_latest_eurusd_candle(self): return {"symbol":"EURUSD","timestamp":"2026-10-06T10:05:00+00:00","open":1.17,"high":1.18,"low":1.16,"close":1.175,"volume":0}
 l=LiveEvaluationLoop(ledger_path=tmp_path/"l.jsonl",client=C()); r=l.step(datetime(2026,10,6,10,12,tzinfo=timezone.utc))
 assert r["status"]=="VALID" and r["feature_cutoff_at"]==r["timestamp"] and r["n_eff"]==1
