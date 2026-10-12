import json

from scripts import live_minute_loop as loop


def test_legacy_metrics_are_archived_and_rebuilt_from_current_ledger(tmp_path, monkeypatch):
    state_path = tmp_path / "live_state.json"
    state_path.write_text(json.dumps({
        "bias": 0.31,
        "resolved": 34,
        "correct": 11,
        "accuracy": 11 / 34,
        "errors": [0.1, -0.2],
        "algorithms": {"MOM_5": {"n": 30, "mae": 0.001}},
        "context_cycles": 42,
        "last_prediction": "2026-10-12T01:02:00+00:00",
    }))
    predictions_path = tmp_path / "predictions.jsonl"
    predictions_path.write_text("\n".join([
        json.dumps({"prediction_id": "clean-1", "data_contract_version": loop.LIVE_DATA_CONTRACT_VERSION,
                    "status": "RESOLVED", "hit": True, "error": 0.1}),
        json.dumps({"prediction_id": "clean-2", "data_contract_version": loop.LIVE_DATA_CONTRACT_VERSION,
                    "status": "RESOLVED", "hit": False, "error": -0.2}),
        json.dumps({"prediction_id": "legacy-1", "status": "RESOLVED", "hit": True, "error": 0.3}),
    ]) + "\n")
    monkeypatch.setattr(loop, "STATE_PATH", state_path)
    monkeypatch.setattr(loop, "PRED_PATH", predictions_path)
    monkeypatch.setattr(loop, "CLAIM_LEDGER_PATH", tmp_path / "ledger.jsonl")

    class FakeLedger:
        def __init__(self, path):
            pass

        def _rows(self):
            return [{"prediction_id": "clean-1"}, {"prediction_id": "clean-2"}]

        def verify(self):
            return True

    monkeypatch.setattr(loop, "Ledger", FakeLedger)
    state = loop.load_state()

    assert state["live_data_contract_version"] == loop.LIVE_DATA_CONTRACT_VERSION
    assert state["resolved"] == 2
    assert state["correct"] == 1
    assert state["accuracy"] == 0.5
    assert state["errors"] == [0.1, -0.2]
    assert state["algorithms"] == {}
    assert state["bias"] == 0.0
    assert state["context_cycles"] == 0
    assert state["last_prediction"] == "2026-10-12T01:02:00+00:00"
    assert state["legacy_pre_contract_metrics"]["resolved"] == 34
    assert state["legacy_pre_contract_metrics"]["correct"] == 11
    assert "not comparable" in state["legacy_pre_contract_metrics"]["note"]


def test_current_contract_metrics_are_not_reset_on_each_load(tmp_path, monkeypatch):
    state_path = tmp_path / "live_state.json"
    state_path.write_text(json.dumps({
        "live_data_contract_version": loop.LIVE_DATA_CONTRACT_VERSION,
        "resolved": 7,
        "correct": 4,
        "accuracy": 4 / 7,
        "errors": [0.1],
        "algorithms": {"MOM_5": {"n": 7, "mae": 0.001}},
        "bias": 0.03,
        "context_cycles": 9,
    }))
    monkeypatch.setattr(loop, "STATE_PATH", state_path)

    state = loop.load_state()

    assert state["resolved"] == 7
    assert state["correct"] == 4
    assert state["accuracy"] == 4 / 7
    assert state["bias"] == 0.03
    assert state["algorithms"]["MOM_5"]["n"] == 7
