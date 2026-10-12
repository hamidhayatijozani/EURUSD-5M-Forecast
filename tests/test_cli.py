import json
from scripts.evidence_cli import main
from tests.evidence_helpers import sample_record


def test_issue_command(tmp_path, capsys):
    row = sample_record()
    rc = main(["--jsonl", str(tmp_path / "ledger.jsonl"), "--db", str(tmp_path / "ledger.db"),
               "issue", "--record-json", json.dumps(row)])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ISSUED"


def test_settle_command_writes_parseable_jsonl_with_one_record_per_line(tmp_path, capsys):
    db_path, jsonl = tmp_path / "ledger.db", tmp_path / "ledger.jsonl"
    settlements = tmp_path / "settlements.jsonl"
    row = sample_record()
    main(["--jsonl", str(jsonl), "--db", str(db_path), "--settlements", str(settlements),
          "issue", "--record-json", json.dumps(row)])
    rc = main(["--jsonl", str(jsonl), "--db", str(db_path), "--settlements", str(settlements),
               "settle", "--prediction-id", row["prediction_id"],
               "--settled-at", "2026-10-12T02:30:01Z", "--settlement-json", '{"actual":0.0001}'])
    assert rc == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["status"] == "RESOLVED"

    raw = settlements.read_text(encoding="utf-8")
    lines = raw.splitlines()
    assert len(lines) == 1
    settled = json.loads(lines[0])
    assert settled["prediction_id"] == row["prediction_id"]
    assert settled["actual"] == 0.0001
    assert settled["settled_at"] == "2026-10-12T02:30:01Z"


def test_audit_command(tmp_path, capsys):
    rc = main(["--jsonl", str(tmp_path / "ledger.jsonl"), "--db", str(tmp_path / "ledger.db"), "audit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["jsonl_valid"] is True
