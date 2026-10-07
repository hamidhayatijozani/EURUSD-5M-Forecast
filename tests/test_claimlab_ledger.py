from datetime import datetime, timedelta, timezone

import pytest

from claimlab.ledger import Ledger
from claimlab.schema import Observation


def make_observation(prediction_id, minute):
    issued = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute)
    target = issued + timedelta(minutes=5)
    resolved = target + timedelta(minutes=1)
    iso = lambda value: value.isoformat().replace("+00:00", "Z")
    return Observation(
        "claimlab.observation.v1", prediction_id, iso(issued), iso(target), iso(resolved),
        "EURUSD", 300, 0.001, 0.002, 0.0, 0.001, 0.002, True,
        0.002, 0.00002, 0.0, 0.0, 0.00198, iso(issued), "test", "cfg", "registry"
    )


def test_batch_append_preserves_hash_chain_and_rejects_duplicates(tmp_path):
    ledger = Ledger(tmp_path / "observations.jsonl")
    first, second = make_observation("p1", 0), make_observation("p2", 1)
    digests = ledger.append_many([first, second])
    assert len(digests) == 2
    assert ledger.verify()
    with pytest.raises(ValueError, match="duplicate prediction_id"):
        ledger.append_many([make_observation("p2", 2)])
    assert ledger.verify()
