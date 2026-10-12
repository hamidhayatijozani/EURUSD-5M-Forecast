import json

from scripts import live_minute_loop as loop


def test_legacy_metrics_are_archived_and_reset_for_current_contract(tmp_path, monkeypatch):
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
    monkeypatch.setattr(loop, "STATE_PATH", state_path)

    state = loop.load_state()

    assert state["live_data_contract_version"] == loop.LIVE_DATA_CONTRACT_VERSION
    assert state["resolved"] == 0
    assert state["correct"] == 0
    assert state["accuracy"] is None
    assert state["errors"] == []
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
