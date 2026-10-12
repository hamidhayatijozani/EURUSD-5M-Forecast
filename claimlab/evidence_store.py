"""Durable forecast evidence ledger backed by SQLite and append-only JSONL."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engine.evidence_contract import validate_temporal_contract, TemporalContractError


class SettlementExistsError(ValueError):
    pass


class TargetNotReachedError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def verify_snapshot(snapshot):
    if not isinstance(snapshot, dict):
        return False
    supplied = snapshot.get("snapshot_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        return False
    payload = {k: v for k, v in snapshot.items() if k != "snapshot_sha256"}
    try:
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return False
    return supplied == expected


def generate_hash(row):
    payload = {k: v for k, v in row.items() if k != "evidence_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def create_row(*, prediction_id, decision_snapshot, **fields):
    if not isinstance(decision_snapshot, dict):
        raise ValueError("DECISION_SNAPSHOT_REQUIRED")
    if not decision_snapshot.get("snapshot_sha256"):
        raise ValueError("SNAPSHOT_SHA256_REQUIRED")
    if not verify_snapshot(decision_snapshot):
        raise ValueError("SNAPSHOT_HASH_MISMATCH")
    row = dict(fields)
    row.update({"prediction_id": str(prediction_id), "decision_snapshot": decision_snapshot})
    validate_temporal_contract(row)
    row["snapshot_sha256"] = decision_snapshot["snapshot_sha256"]
    row["evidence_hash"] = generate_hash(row)
    return row


class JsonLedger:
    """Append-only JSONL writer with hash-chain verification."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rows(self):
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def append(self, record):
        validate_temporal_contract(record)
        if not record.get("decision_snapshot") or not record.get("snapshot_sha256") or not record.get("evidence_hash"):
            raise ValueError("EVIDENCE_FIELDS_REQUIRED")
        if record["snapshot_sha256"] != record["decision_snapshot"].get("snapshot_sha256") or not verify_snapshot(record["decision_snapshot"]):
            raise ValueError("SNAPSHOT_HASH_MISMATCH")
        if generate_hash(record) != record["evidence_hash"]:
            raise ValueError("EVIDENCE_HASH_MISMATCH")
        rows = self._rows()
        if any(row.get("prediction_id") == record.get("prediction_id") for row in rows):
            raise ValueError("DUPLICATE_PREDICTION_ID")
        previous = rows[-1].get("ledger_hash", "") if rows else ""
        body = dict(record)
        body["previous_hash"] = previous
        body["ledger_hash"] = hashlib.sha256((previous + canonical_json(record)).encode("utf-8")).hexdigest()
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(body) + "\n")
            handle.flush()
        return record["prediction_id"]

    def verify(self):
        previous = ""
        for row in self._rows():
            supplied = row.get("ledger_hash")
            record = {k: v for k, v in row.items() if k not in ("previous_hash", "ledger_hash")}
            if row.get("previous_hash", "") != previous or generate_hash(record) != record.get("evidence_hash"):
                return False
            if record.get("snapshot_sha256") != record.get("decision_snapshot", {}).get("snapshot_sha256") or not verify_snapshot(record.get("decision_snapshot")):
                return False
            expected = hashlib.sha256((previous + canonical_json(record)).encode("utf-8")).hexdigest()
            if supplied != expected:
                return False
            previous = expected
        return True


class LedgerDB:
    """SQLite store; predictions and snapshots are immutable, settlements unique."""
    def __init__(self, path=":memory:"):
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS predictions (
          prediction_id TEXT PRIMARY KEY,
          issued_at TEXT NOT NULL,
          target_ts TEXT NOT NULL,
          feature_cutoff_at TEXT NOT NULL,
          evidence_hash TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS snapshots (
          prediction_id TEXT PRIMARY KEY REFERENCES predictions(prediction_id),
          snapshot_sha256 TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settlements (
          prediction_id TEXT PRIMARY KEY REFERENCES predictions(prediction_id),
          settled_at TEXT NOT NULL,
          payload_json TEXT NOT NULL
        );
        """)

    def insert_prediction(self, record):
        validate_temporal_contract(record)
        if not record.get("evidence_hash") or not record.get("decision_snapshot"):
            raise ValueError("EVIDENCE_FIELDS_REQUIRED")
        if record.get("snapshot_sha256") != record["decision_snapshot"].get("snapshot_sha256") or not verify_snapshot(record["decision_snapshot"]):
            raise ValueError("SNAPSHOT_HASH_MISMATCH")
        if generate_hash(record) != record["evidence_hash"]:
            raise ValueError("EVIDENCE_HASH_MISMATCH")
        pid = str(record["prediction_id"])
        self.connection.execute(
            "INSERT INTO predictions VALUES (?, ?, ?, ?, ?, ?)",
            (pid, record["issued_at"], record["target_ts"], record["feature_cutoff_at"],
             record["evidence_hash"], canonical_json(record)),
        )
        self.connection.commit()
        return pid

    def get_prediction(self, prediction_id):
        return self.connection.execute("SELECT * FROM predictions WHERE prediction_id=?", (prediction_id,)).fetchone()

    def insert_snapshot(self, prediction_id, snapshot):
        if not isinstance(snapshot, dict) or not snapshot.get("snapshot_sha256"):
            raise ValueError("SNAPSHOT_SHA256_REQUIRED")
        if not verify_snapshot(snapshot):
            raise ValueError("SNAPSHOT_HASH_MISMATCH")
        supplied = snapshot["snapshot_sha256"]
        prediction = self.get_prediction(prediction_id)
        if prediction is None:
            raise ValueError("UNKNOWN_PREDICTION")
        payload = json.loads(prediction["payload_json"])
        if payload.get("snapshot_sha256") != supplied:
            raise ValueError("SNAPSHOT_REFERENCE_MISMATCH")
        self.connection.execute("INSERT INTO snapshots VALUES (?, ?, ?)",
                                (prediction_id, supplied, canonical_json(snapshot)))
        self.connection.commit()

    def get_snapshot(self, prediction_id):
        return self.connection.execute("SELECT * FROM snapshots WHERE prediction_id=?", (prediction_id,)).fetchone()

    def insert_settlement(self, prediction_id, settlement=None, *, settled_at=None):
        pred = self.get_prediction(prediction_id)
        if pred is None:
            raise ValueError("UNKNOWN_PREDICTION")
        settlement = dict(settlement or {})
        settled = settled_at or settlement.get("settled_at")
        if not settled:
            raise ValueError("SETTLED_AT_REQUIRED")
        dt = lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt(settled).astimezone(timezone.utc) < dt(pred["target_ts"]).astimezone(timezone.utc):
            raise TargetNotReachedError("TARGET_NOT_REACHED")
        try:
            self.connection.execute("INSERT INTO settlements VALUES (?, ?, ?)",
                                    (prediction_id, str(settled), canonical_json(settlement)))
            self.connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SettlementExistsError("SETTLEMENT_ALREADY_EXISTS") from exc
        return prediction_id

    def close(self):
        self.connection.close()
