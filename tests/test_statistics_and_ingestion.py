from claimlab.statistics import StatisticalEngine
from claimlab.ingestion import MarketIngestionClient, YahooEURUSD5mClient


def test_effective_n_reduces_for_persistent_series():
    values = [float(i % 5) for i in range(200)]
    neff = StatisticalEngine.calculate_effective_n(values, horizon=5)
    assert 1 <= neff <= len(values)


def test_bh_preserves_original_order():
    assert StatisticalEngine.benjamini_hochberg_correction([0.001, 0.9, 0.002]) == [True, False, True]


def test_ohlc_validation_rejects_invalid_candle():
    bad = {
        "symbol": "EURUSD", "timestamp": "2026-10-06T10:00:00Z",
        "open": 1.2, "high": 1.1, "low": 1.0, "close": 1.05, "volume": 0
    }
    try:
        MarketIngestionClient._validate_candle(bad)
    except ValueError:
        return
    raise AssertionError("invalid OHLC was accepted")


def test_yahoo_adapter_normalizes_chart_payload():
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"chart": {"result": [{
                "timestamp": [1791280800],
                "indicators": {"quote": [{
                    "open": [1.17], "high": [1.18], "low": [1.16],
                    "close": [1.175], "volume": [0]
                }]}
            }]}}

    class FakeSession:
        def get(self, endpoint, timeout):
            return FakeResponse()

    candle = YahooEURUSD5mClient(session=FakeSession()).fetch_latest_eurusd_candle()
    assert candle["symbol"] == "EURUSD"
    assert candle["close"] == 1.175
