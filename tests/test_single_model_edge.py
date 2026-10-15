from datetime import datetime, timedelta, timezone

from scripts.run_single_model_edge import FEATURES, make_samples


def _rows(n=100):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    close = 1.1
    for i in range(n):
        ts = start + timedelta(minutes=5 * i)
        nxt = close * (1 + (0.0002 if i % 3 else -0.0001))
        rows.append({
            "timestamp": ts, "open": close, "high": max(close, nxt) + 0.00005,
            "low": min(close, nxt) - 0.00005, "close": nxt, "volume": float(i + 1),
        })
        close = nxt
    return rows


def test_fixed_feature_count_and_no_target_bar_leakage():
    rows = _rows()
    samples = make_samples(rows)
    assert len(FEATURES) == 10
    assert len(samples[0]["x"]) == 10
    original = samples[0]
    changed = [dict(r) for r in rows]
    target_index = 61
    changed[target_index]["close"] *= 1.02
    changed_samples = make_samples(changed)
    assert original["x"] == changed_samples[0]["x"]
    assert original["actual_return"] != changed_samples[0]["actual_return"]


def test_gap_bar_is_not_used_as_a_next_five_minute_target():
    rows = _rows()
    rows[62]["timestamp"] += timedelta(minutes=5)
    samples = make_samples(rows)
    assert all(
        s["timestamp"] + timedelta(minutes=5) == rows[i + 1]["timestamp"]
        for i, s in enumerate(samples)
        if i + 1 < len(samples) and s["timestamp"] == rows[i]["timestamp"]
    )
