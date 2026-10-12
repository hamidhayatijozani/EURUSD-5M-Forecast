"""CLI for issuing, settling, auditing, and verifying evidence ledger rows."""
import argparse
import json
from pathlib import Path

from claimlab.evidence_store import JsonLedger, LedgerDB, create_row


def _parser():
    parser = argparse.ArgumentParser(prog="evidence-ledger")
    parser.add_argument("--jsonl", default="live/evidence_ledger.jsonl")
    parser.add_argument("--db", default="live/evidence.db")
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
    try:
        if args.command == "issue":
            record = json.loads(args.record_json)
            # Rebuild canonical hash only if the supplied record has not been hashed.
            if not record.get("evidence_hash"):
                record = create_row(**record)
            ledger.append(record)
            db.insert_prediction(record)
            db.insert_snapshot(record["prediction_id"], record["decision_snapshot"])
            print(json.dumps({"status": "ISSUED", "prediction_id": record["prediction_id"]}))
        elif args.command == "settle":
            settlement = json.loads(args.settlement_json)
            settlement["settled_at"] = args.settled_at
            db.insert_settlement(args.prediction_id, settlement, settled_at=args.settled_at)
            Path("live/settlements.jsonl").parent.mkdir(parents=True, exist_ok=True)
            with Path("live/settlements.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"prediction_id": args.prediction_id, **settlement}, sort_keys=True) + "\n")
            print(json.dumps({"status": "RESOLVED", "prediction_id": args.prediction_id}))
        elif args.command == "audit":
            ok = ledger.verify()
            print(json.dumps({"status": "AUDITED" if ok else "INTEGRITY_FAILURE", "jsonl_valid": ok}))
            return 0 if ok else 2
        elif args.command == "coverage":
            rows = ledger._rows()
            print(json.dumps({"records": len(rows), "with_snapshot": sum(bool(r.get("decision_snapshot")) for r in rows)}))
        elif args.command == "verify":
            ok = ledger.verify()
            print(json.dumps({"status": "VERIFIED" if ok else "INTEGRITY_FAILURE"}))
            return 0 if ok else 2
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
