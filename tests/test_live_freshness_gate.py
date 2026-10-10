"""Behavioural regression tests for the live loop's data-freshness gate.

They run the real ``cycle()`` and the real feed adapter. Only these are replaced:
the network boundary (``fetch_1m_ohlc``), external-context collection, the clock
and the evidence file paths. Written with ``unittest`` so they run under the
repo's pytest CI as well as under plain ``python -m unittest``.

Convention under test: Yahoo labels a 1-minute candle by its OPEN time. Data age is
the time since the candle CLOSED (open + 1 minute) and the contract limit is 90 s.
"""
import contextlib
import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import engine.live_feed as feed
import scripts.live_minute_loop as loop

LIMIT_SECONDS = 90.0
T0 = datetime(2026, 10, 9, 10, 7, 30, tzinfo=timezone.utc)  # cycle start ("now")
# Seconds since the newest candle CLOSED, as seen at T0.
AGES = [0, 10, 29, 30, 31, 45, 60, 75, 85, 89, 90, 91, 120, 150]


class _Clock:
    def __init__(self, now):
        self.now = now


def _fake_datetime(clock):
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock.now.astimezone(tz) if tz else clock.now

    return FakeDatetime


def _candles(age_since_close, n=120):
    """n consecutive 1m candles labelled by OPEN time; the newest closed
    ``age_since_close`` seconds before T0."""
    newest_open = T0 - timedelta(seconds=age_since_close + 60)
    rows = []
    for i in range(n):
        ts = newest_open - timedelta(minutes=n - 1 - i)
        p = 1.1000 + 0.00004 * ((i * 7) % 11 - 5) + 0.000001 * i
        rows.append((ts, p, p + 0.0002, p - 0.0002, p))
    return rows


def run_cycle(age_since_close, per_fetch_latency=0.0):
    """Run the real cycle(); return (exception_or_None, persisted_prediction_rows).

    ``per_fetch_latency`` advances the fake clock on every HTTP fetch, so the
    observation time ends up later than the cycle start, as it does live."""
    clock = _Clock(T0)

    def fake_fetch(symbol="EURUSD"):
        rows = _candles(age_since_close)
        clock.now += timedelta(seconds=per_fetch_latency)
        return rows

    with tempfile.TemporaryDirectory() as tmp, \
            mock.patch.dict(os.environ), \
            mock.patch.object(feed, "fetch_1m_ohlc", fake_fetch), \
            mock.patch.object(loop, "datetime", _fake_datetime(clock)), \
            mock.patch.object(loop, "collect_external_context",
                              lambda *a, **k: {"context_score": 0.0, "power_score": 0.0}), \
            mock.patch.object(loop, "STATE_PATH", Path(tmp) / "state.json"), \
            mock.patch.object(loop, "PRED_PATH", Path(tmp) / "predictions.jsonl"), \
            mock.patch.object(loop, "CLAIM_LEDGER_PATH", Path(tmp) / "ledger.jsonl"):
        os.environ.pop("GITHUB_ACTIONS", None)  # never git-commit from a test
        error = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                loop.cycle()
        except Exception as exc:  # noqa: BLE001 - the tests inspect the error
            error = exc
        rows = loop.read_predictions()
    return error, rows


def feed_accepts(age_since_close):
    """True if the feed adapter alone treats a candle this old as fresh."""
    with mock.patch.object(feed, "fetch_1m_ohlc", lambda symbol="EURUSD": _candles(age_since_close)):
        try:
            feed.aligned_closed_1m_series(T0)
            feed.aligned_closed_1m_ohlc(T0)
        except RuntimeError:
            return False
    return True


class FreshnessGateTests(unittest.TestCase):
    def assert_accepted(self, age, **kwargs):
        error, rows = run_cycle(age, **kwargs)
        self.assertIsNone(error, f"candle that closed {age}s ago was rejected: {error!r}")
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_145s_and_149s_since_candle_open_are_fresh(self):
        # 145 s / 149 s since OPEN are 85 s / 89 s since CLOSE: inside the contract.
        for since_open in (145, 149):
            row = self.assert_accepted(since_open - 60)
            self.assertAlmostEqual(row["data_age_seconds"], since_open - 60, places=6)

    def test_exactly_90s_since_close_is_accepted(self):
        self.assert_accepted(90.0)

    def test_91s_since_close_is_rejected_and_nothing_is_persisted(self):
        error, rows = run_cycle(91)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("STALE", str(error))
        self.assertEqual(rows, [])

    def test_data_the_feed_accepts_is_never_rejected_by_the_loop(self):
        # Root cause of the live failures: the adapter measured age from candle
        # CLOSE, the loop from candle OPEN, so 30 s < age <= 90 s passed one gate
        # and failed the other.
        disagreements = []
        for age in AGES:
            if feed_accepts(age):
                error, _ = run_cycle(age)
                if error is not None:
                    disagreements.append((age, repr(error)))
        self.assertEqual(disagreements, [], "feed accepted but loop rejected: (age since close, error)")

    def test_no_accepted_prediction_carries_stale_evidence(self):
        bad = []
        for latency in (0.0, 2.0):
            for age in AGES:
                error, rows = run_cycle(age, per_fetch_latency=latency)
                if error is not None:
                    continue
                row = rows[-1]
                seen = row.get("data_age_seconds")
                if seen is None or seen > row.get("freshness_limit_seconds", LIMIT_SECONDS):
                    bad.append((age, latency, seen))
        self.assertEqual(bad, [], "accepted prediction with missing or stale evidence: (age, latency, recorded age)")

    def test_prediction_row_evidence_is_internally_consistent(self):
        row = self.assert_accepted(60.0, per_fetch_latency=1.5)
        opened = datetime.fromisoformat(row["source_candle_ts"])
        observed = datetime.fromisoformat(row["observed_at"])
        # Independent oracle: age = observed_at - (candle open + 1 minute).
        expected = (observed - (opened + timedelta(minutes=1))).total_seconds()
        self.assertAlmostEqual(row["data_age_seconds"], expected, places=6)
        self.assertEqual(row["provider"], "Yahoo")
        self.assertEqual(row["freshness_limit_seconds"], LIMIT_SECONDS)
        self.assertEqual(row["freshness_status"], "FRESH")
        self.assertLessEqual(row["data_age_seconds"], row["freshness_limit_seconds"])
        self.assertEqual(row["data_contract_version"], loop.LIVE_DATA_CONTRACT_VERSION)

    def test_contract_label_was_bumped_when_age_semantics_changed(self):
        self.assertNotEqual(loop.LIVE_DATA_CONTRACT_VERSION, "freshness-90s-v1")

    def test_pending_rows_from_the_v1_contract_are_quarantined(self):
        rows = [
            {"prediction_id": "v1", "status": "PENDING", "data_contract_version": "freshness-90s-v1"},
            {"prediction_id": "cur", "status": "PENDING",
             "data_contract_version": loop.LIVE_DATA_CONTRACT_VERSION},
        ]
        self.assertTrue(loop._quarantine_legacy_predictions(rows))
        self.assertEqual(rows[0]["status"], "EXCLUDED_PRE_CONTRACT")
        self.assertEqual(rows[1]["status"], "PENDING")

    def test_issued_prediction_resolves_into_a_ledger_entry_with_its_freshness_evidence(self):
        # A live run is only healthy if the evidence also survives settlement five
        # minutes later, not just the freshness gate at issue time.
        from claimlab.ledger import Ledger

        error, rows = run_cycle(60.0, per_fetch_latency=1.5)
        self.assertIsNone(error, repr(error))
        row = rows[0]
        target_open = datetime.fromisoformat(row["target_ts"])
        times = [target_open - timedelta(minutes=1), target_open]
        prices = [row["entry_price"], row["entry_price"] * 1.0003]
        state = {"bias": 0.0, "resolved": 0, "correct": 0, "errors": [], "algorithms": {}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(loop, "CLAIM_LEDGER_PATH", Path(tmp) / "ledger.jsonl"):
            self.assertTrue(loop.settle([row], times, prices, state, "test-sha"))
            ledger = Ledger(loop.CLAIM_LEDGER_PATH)
            self.assertTrue(ledger.verify())
            entries = ledger._rows()
        self.assertEqual(row["status"], "RESOLVED")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        for key in ("source_candle_ts", "observed_at", "data_age_seconds",
                    "freshness_limit_seconds", "freshness_status"):
            self.assertEqual(entry[key], row[key], key)
        self.assertGreater(entry["data_age_seconds"], 0.0)  # the real age, not the 0.0 default


class FeedDiagnosticsTests(unittest.TestCase):
    def test_http_status_and_reason_are_exposed(self):
        err = HTTPError("https://example.invalid/chart", 429, "Too Many Requests", None, None)
        with mock.patch.object(feed, "fetch_1m_ohlc", mock.Mock(side_effect=err)):
            with self.assertRaises(RuntimeError) as ctx:
                feed.aligned_closed_1m_series(T0)
        message = str(ctx.exception)
        self.assertIn("429", message)
        self.assertIn("Too Many Requests", message)
        self.assertIs(ctx.exception.__cause__, err)

    def test_non_http_failures_keep_type_and_message(self):
        with mock.patch.object(feed, "fetch_1m_ohlc", mock.Mock(side_effect=TimeoutError("timed out"))):
            with self.assertRaises(RuntimeError) as ctx:
                feed.aligned_closed_1m_series(T0)
        message = str(ctx.exception)
        self.assertIn("TimeoutError", message)
        self.assertIn("timed out", message)


if __name__ == "__main__":
    unittest.main()
