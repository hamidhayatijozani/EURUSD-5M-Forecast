import unittest

from claimlab.live_provenance import require_freshness_provenance


class LiveFreshnessProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "provider": "yahoo",
            "source_candle_ts": "2026-10-27T13:12:00+00:00",
            "observed_at": "2026-10-27T13:12:47+00:00",
            "data_age_seconds": 47.0,
            "freshness_limit_seconds": 90.0,
            "freshness_status": "FRESH",
        }

    def test_accepts_complete_fresh_provenance(self):
        result = require_freshness_provenance(self.row)
        self.assertEqual(result["provider"], "yahoo")
        self.assertEqual(result["data_age_seconds"], 47.0)

    def test_missing_age_is_rejected_instead_of_defaulted(self):
        row = dict(self.row)
        del row["data_age_seconds"]
        with self.assertRaisesRegex(ValueError, "LIVE_FRESHNESS_PROVENANCE_MISSING:data_age_seconds"):
            require_freshness_provenance(row)

    def test_stale_or_nonfinite_age_is_rejected(self):
        for age in (91.0, float("nan"), float("inf"), -1.0):
            row = dict(self.row, data_age_seconds=age)
            with self.subTest(age=age), self.assertRaises(ValueError):
                require_freshness_provenance(row)

    def test_naive_or_future_source_timestamp_is_rejected(self):
        row = dict(self.row, source_candle_ts="2026-10-27T13:13:00+00:00")
        with self.assertRaisesRegex(ValueError, "LIVE_FRESHNESS_SOURCE_FROM_FUTURE"):
            require_freshness_provenance(row)
        row = dict(self.row, observed_at="2026-10-27T13:12:47")
        with self.assertRaisesRegex(ValueError, "LIVE_FRESHNESS_TIMESTAMP_MUST_BE_TIMEZONE_AWARE"):
            require_freshness_provenance(row)


if __name__ == "__main__":
    unittest.main()
