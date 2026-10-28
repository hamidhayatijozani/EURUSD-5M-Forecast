import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_historical_provenance import audit_ledger


class HistoricalProvenanceAuditTests(unittest.TestCase):
    def test_missing_provenance_is_excluded_without_defaults(self):
        rows = [
            {"prediction_id": "good", "provider": "feed-a",
             "source_candle_ts": "2026-10-27T10:00:00+00:00",
             "observed_at": "2026-10-27T10:00:20+00:00",
             "data_age_seconds": 20, "freshness_status": "FRESH"},
            {"prediction_id": "unknown", "provider": "feed-a",
             "source_candle_ts": "2026-10-27T10:00:00+00:00"},
        ]
        raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            path.write_bytes(raw)
            report = audit_ledger(path)
            self.assertEqual(report["raw_rows"], 2)
            self.assertEqual(report["eligible_rows"], 1)
            self.assertEqual(report["excluded_rows"], 1)
            excluded = report["rows"][1]
            self.assertEqual(excluded["row_id"], "unknown")
            self.assertEqual(set(excluded["missing_fields"]),
                             {"observed_at", "data_age_seconds", "freshness_status"})
            self.assertFalse(excluded["metric_inclusion"]["forecast_metrics"])
            self.assertNotIn("data_age_seconds", excluded)
            self.assertEqual(path.read_bytes(), raw)

    def test_missing_age_never_becomes_zero_or_fresh(self):
        raw = (json.dumps({"id": "x", "source": "feed", "timestamp": "2026-10-27T10:00:00Z",
                           "observed_at": "2026-10-27T10:00:01Z"}) + "\n").encode()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            path.write_bytes(raw)
            row = audit_ledger(path)["rows"][0]
            self.assertIn("data_age_seconds", row["missing_fields"])
            self.assertIn("freshness_status", row["missing_fields"])
            self.assertEqual(row["status"], "EXCLUDED_PROVENANCE_UNKNOWN")

    def test_source_hash_is_of_exact_original_bytes(self):
        raw = b'{"id":"x"}\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            path.write_bytes(raw)
            report = audit_ledger(path)
            self.assertEqual(report["source_file_sha256"], hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
