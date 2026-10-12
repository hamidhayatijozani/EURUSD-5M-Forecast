"""Command-line entry point for the cross-store evidence audit."""
import argparse
import json
from scripts.audit_evidence_ledger import audit

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", default="live/evidence_ledger.jsonl")
    parser.add_argument("--db", default="live/evidence.db")
    parser.add_argument("--settlements", default="live/settlements.jsonl")
    args = parser.parse_args(argv)
    result = audit(args.jsonl, args.db, args.settlements)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "AUDITED" else 2

if __name__ == "__main__":
    raise SystemExit(main())
