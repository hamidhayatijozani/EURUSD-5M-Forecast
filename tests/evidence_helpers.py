import hashlib
import json


def sample_snapshot():
    payload = {
        "schema": "test.snapshot.v1",
        "feature_cutoff_at": "2026-10-12T02:24:59Z",
        "issued_at": "2026-10-12T02:25:00Z",
        "target_ts": "2026-10-12T02:30:00Z",
        "inputs": {"EURUSD": [1.15, 1.155]},
    }
    payload["snapshot_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()
    return payload


def sample_record(prediction_id="p-001"):
    from claimlab.evidence_store import create_row
    return create_row(
        prediction_id=prediction_id,
        decision_snapshot=sample_snapshot(),
        feature_cutoff_at="2026-10-12T02:24:59Z",
        issued_at="2026-10-12T02:25:00Z",
        target_ts="2026-10-12T02:30:00Z",
        forecast_direction="UP",
        forecast_price=1.155,
    )
