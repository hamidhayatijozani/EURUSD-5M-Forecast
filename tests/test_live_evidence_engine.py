from claimlab.evidence_capsule import EvidenceCapsuleGenerator
from claimlab.state_machine import ClaimState, ClaimStateMachine
from claimlab.live_ledger import AppendOnlyLedger
from claimlab.replay import LedgerReplayEngine

def test_temporal_boundaries():
    assert EvidenceCapsuleGenerator.verify_temporal_integrity(
        "2026-10-06T10:00:00Z", "2026-10-06T10:04:59Z", "2026-10-06T10:05:00Z")
    assert not EvidenceCapsuleGenerator.verify_temporal_integrity(
        "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z", "2026-10-06T10:05:00Z")

def test_capsule_hash_is_deterministic_except_ingestion_time(tmp_path):
    c = EvidenceCapsuleGenerator.create_capsule(
        {"timestamp":"2026-10-06T10:00:00Z","open":1,"high":2,"low":0.5,"close":1.5},
        "2026-10-06T10:00:00Z", 10, 8.5, {"horizon":5}, "abc", "commit", "0"*64)
    assert len(c["current_hash"]) == 64
    assert c["previous_hash"] == "0"*64

def test_state_machine_does_not_treat_zero_p_as_missing():
    sm = ClaimStateMachine("C001", min_effective_n=30)
    assert sm.evaluate(30, {"p_value":0.0,"ci_lower":0.01,"bh_significant":True}) is ClaimState.SUPPORTED
    assert ClaimStateMachine("C001", 30).evaluate(29, {"p_value":0.0,"ci_lower":1}) is ClaimState.INSUFFICIENT_DATA

def test_state_machine_kill_is_terminal():
    sm = ClaimStateMachine("C001"); sm.kill()
    assert sm.evaluate(100, {"p_value":0.0,"ci_lower":1,"bh_significant":True}) is ClaimState.KILLED

def test_replay_uses_same_ledger_hash_contract(tmp_path):
    path = tmp_path/"ledger.jsonl"
    ledger = AppendOnlyLedger(path)
    ledger.append({"timestamp":"2026-10-06T10:00:00Z","candle_timestamp":"2026-10-06T10:00:00Z",
                   "feature_cutoff_at":"2026-10-06T10:00:00Z","n_raw":1,"n_eff":1})
    assert ledger.verify()
    engine = LedgerReplayEngine(str(path), "claimlab/registry.lock")
    assert engine.verify_ledger_integrity()
