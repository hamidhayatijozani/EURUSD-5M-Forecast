from engine.trader_intelligence import consensus_from_top_traders, rank_top_traders

AS_OF = "2026-10-05T10:00:00Z"
WINDOW_START = "2026-10-03T10:00:00Z"


def trade(side="BUY", profit=5.0, close_timestamp="2026-10-05T09:00:00Z", symbol="EURUSD"):
    return {
        "symbol": symbol,
        "side": side,
        "profit": profit,
        "closeTimestamp": close_timestamp,
    }


def record(identifier="T1", **kwargs):
    data = {
        "id": identifier,
        "name": f"Trader {identifier}",
        "maxDrawdown48h": 5,
        "consistency48h": 0.8,
        "trades": [trade()],
    }
    data.update(kwargs)
    return data


def test_ranker_uses_only_valid_eurusd_trades_in_closed_48h_window():
    item = record(trades=[
        trade("BUY", 10.0, "2026-10-05T09:00:00Z"),
        trade("SELL", 2.0, "2026-10-05T08:00:00Z"),
        trade("BUY", 9999.0, "2026-10-01T00:00:00Z"),  # Too old
        trade("BUY", 9999.0, "2026-10-05T10:00:01Z"),  # Future
        trade("BUY", 9999.0, "2026-10-05T09:00:00Z", symbol="EURJPY"),
        trade("BUY", float("inf"), "2026-10-05T09:00:00Z"),
        {"symbol": "EURUSD", "side": "BUY", "profit": 500},  # Missing timestamp
    ])

    ranked = rank_top_traders([item], AS_OF)

    assert len(ranked) == 1
    stats = ranked[0]["window"]
    assert stats["trades"] == 2
    assert stats["net_profit"] == 12.0
    assert stats["net_long_profit"] == 8.0
    assert stats["wins"] == 2
    assert stats["profit_factor_unbounded"] is True
    assert stats["profit_factor"] is None
    assert ranked[0]["rank"] == 1
    assert ranked[0]["window"]["start"] == WINDOW_START
    assert ranked[0]["window"]["end"] == AS_OF


def test_window_boundaries_are_inclusive_and_missing_quality_is_penalized():
    boundary = trade("BUY", 1.0, WINDOW_START)
    with_quality = record("complete", trades=[boundary, trade("BUY", 2.0)],
                          maxDrawdown48h=0, consistency48h=1.0)
    missing_quality = record("missing", trades=[boundary, trade("BUY", 2.0)],
                             maxDrawdown48h=None, consistency48h=None)

    ranked = rank_top_traders([missing_quality, with_quality], AS_OF)

    assert [x["id"] for x in ranked] == ["complete", "missing"]
    missing = ranked[1]
    assert missing["window"]["trades"] == 2
    assert missing["score_components"]["drawdown_quality"] == 0.0
    assert missing["score_components"]["consistency"] == 0.0
    assert missing["quality_warnings"] == [
        "MISSING_48H_DRAWDOWN", "MISSING_48H_CONSISTENCY"
    ]
    assert ranked[0]["score"] > missing["score"]


def test_old_future_wrong_symbol_and_nonpositive_net_records_are_excluded():
    records = [
        record("old", trades=[trade(close_timestamp="2026-10-01T00:00:00Z")]),
        record("future", trades=[trade(close_timestamp="2026-10-05T10:01:00Z")]),
        record("wrong-symbol", trades=[trade(symbol="GBPUSD")]),
        record("negative", trades=[trade(profit=-1)]),
        record("zero", trades=[trade(profit=0)]),
        record("bad-side", trades=[trade(side="HOLD")]),
        record("missing-id", id="", trades=[trade()]),
    ]

    assert rank_top_traders(records, AS_OF) == []


def test_score_is_bounded_and_limit_is_deterministic():
    records = [
        record(f"T{i:02d}", trades=[trade(profit=10 - i / 100)])
        for i in range(60)
    ]

    ranked = rank_top_traders(records, AS_OF, limit=50)

    assert len(ranked) == 50
    assert [item["rank"] for item in ranked] == list(range(1, 51))
    assert all(0 <= item["score"] <= 100 for item in ranked)
    assert all(ranked[i]["score"] >= ranked[i + 1]["score"] for i in range(49))
    assert "T59" not in {item["id"] for item in ranked}


def test_consensus_is_bounded_and_empty_coverage_is_explicit():
    empty = consensus_from_top_traders([])
    assert empty == {
        "status": "UNAVAILABLE_NO_ELIGIBLE_TRADERS",
        "score": 0.0,
        "coverage": 0,
    }

    consensus = consensus_from_top_traders([
        {"score": 80, "window": {"net_long_profit": 10}},
        {"score": 40, "window": {"net_long_profit": -5}},
        {"score": 70, "window": {"net_long_profit": 0}},
    ])
    assert consensus["status"] == "RESEARCH_ONLY"
    assert consensus["coverage"] == 3
    assert -1 <= consensus["score"] <= 1
    assert consensus["score"] == 0.210526


def test_rejects_ambiguous_asof_time_and_invalid_limit():
    try:
        rank_top_traders([], "2026-10-05T10:00:00")
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("timezone-naive as-of must be rejected")

    for limit in (0, -1, True, 1.5):
        try:
            rank_top_traders([], AS_OF, limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid limit accepted: {limit!r}")
