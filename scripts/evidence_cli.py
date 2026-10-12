"""CLI for issuing, settling, auditing, and verifying evidence ledger rows."""
import argparse
import json
from pathlib import Path

from claimlab.evidence_store import JsonLedger, LedgerDB, create_row


def _parser():
    parser = argparse.ArgumentParser(prog="evidence-ledger")
    parser.add_argument("--jsonl", default="live/evidence_ledger.jsonl")
    parser.add_argument("--db", default="live/evidence.db")
    parser.add_argument("--settlements", default="live/settlements.jsonl")
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue")
    issue.add_argument("--record-json", required=True)
    settle = sub.add_parser("settle")
    settle.add_argument("--prediction-id", required=True)
    settle.add_argument("--settled-at", required=True)
    settle.add_argument("--settlement-json", default="{}")
    sub.add_parser("audit")
    sub.add_parser("coverage")
    sub.add_parser("verify")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    ledger = JsonLedger(args.jsonl)
    db = LedgerDB(args.db)
    settlement_path = Path(args.settlements)
    try:
        if args.command == "issue":
            record = json.loads(args.record_json)
            if not record.get("evidence_hash"):
                record = create_row(**record)
            # The two storage systems cannot share one transaction. Audit detects
            # any partial write rather than pretending it was atomic.
            db.insert_prediction(record)
            db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
            ledger.append(record)
            print(json.dumps({"status": "ISSUED", "prediction_id": record["prediction_id"]}))
        elif args.command == "settle":
            settlement = json.loads(args.settlement_json)
            settlement["settled_at"] = args.settled_at
            db.insert_settlement(args.prediction_id, settlement, settled_at=args.settled_at)
            settlement_path.parent.mkdir(parents=True, exist_ok=True)
            with settlement_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"prediction_id": args.prediction_id, **settlement}, sort_keys=True) + "\n")
                handle.flush()
            print(json.dumps({"status": "RESOLVED", "prediction_id": args.prediction_id}))
        elif args.command in ("audit", "verify"):
            rows = ledger._rows()
            jsonl_ok = ledger.verify()
            prediction_count = db.connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            snapshot_count = db.connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            settlement_orphans = db.connection.execute(
                "SELECT COUNT(*) FROM settlements s LEFT JOIN predictions p USING(prediction_id) WHERE p.prediction_id IS NULL"
            ).fetchone()[0]
            stores_match = prediction_count == len(rows) == snapshot_count and settlement_orphans == 0
            ok = jsonl_ok and stores_match
            print(json.dumps({
                "status": "AUDITED" if ok else "INTEGRITY_FAILURE",
                "jsonl_valid": jsonl_ok,
                "sqlite_stores_match": stores_match,
                "jsonl_predictions": len(rows),
                "sqlite_predictions": prediction_count,
                "sqlite_snapshots": snapshot_count,
                "orphan_settlements": settlement_orphans,
            }, sort_keys=True))
            return 0 if ok else 2
        elif args.command == "coverage":
            rows = ledger._rows()
            snapshots = db.connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            settlements = db.connection.execute("SELECT COUNT(*) FROM settlements").fetchone()[0]
            print(json.dumps({"records": len(rows), "with_snapshot": snapshots, "settlements": settlements}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
