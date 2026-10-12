from datetime import datetime, timedelta, timezone

from engine.grid_power_proxy import grid_load_features


def test_grid_proxy_uses_only_observations_available_at_forecast_time():
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    rows = [{"timestamp": (now - timedelta(minutes=5 * i)).isoformat(),
             "value": 100.0, "region": "DE", "unit": "MW"}
            for i in range(1, 14)]
    rows += [{"timestamp": (now + timedelta(minutes=5)).isoformat(),
              "value": 500.0, "region": "DE", "unit": "MW"}]
    rows.append({"timestamp": now.isoformat(), "value": 115.0, "region": "DE", "unit": "MW"})
    out = grid_load_features(rows, now, max_age_seconds=600, min_history=12)
    assert out["status"] == "OK"
    assert out["load_value"] == 115.0
    assert out["baseline_value"] == 100.0
    assert abs(out["score"] - 1.0) < 1e-12
    assert out["directional"] is False


def test_grid_proxy_rejects_stale_and_insufficient_history():
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    stale = [{"timestamp": (now - timedelta(hours=2)).isoformat(),
              "value": 100, "region": "GB", "unit": "MW"}]
    assert grid_load_features(stale, now, max_age_seconds=1800)["status"] == "STALE"
    short = [{"timestamp": (now - timedelta(minutes=5 * i)).isoformat(),
              "value": 100, "region": "GB", "unit": "MW"} for i in range(4, -1, -1)]
    assert grid_load_features(short, now, min_history=12)["status"] == "INSUFFICIENT_HISTORY"


def test_grid_proxy_separates_regions_and_units():
    now = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
    rows = []
    for i in range(14, 0, -1):
        rows.append({"timestamp": (now - timedelta(minutes=5 * i)).isoformat(),
                     "value": 100, "region": "DE", "unit": "MW"})
    rows.append({"timestamp": now.isoformat(), "value": 1000, "region": "GB", "unit": "MW"})
    out = grid_load_features(rows, now, min_history=12)
    assert out["status"] == "INSUFFICIENT_HISTORY"
    assert out["directional"] is False
