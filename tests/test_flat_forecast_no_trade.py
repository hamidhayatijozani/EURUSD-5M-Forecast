import unittest
from types import SimpleNamespace
from unittest.mock import patch

import scripts.live_minute_loop as loop


class FlatForecastNoTradeTests(unittest.TestCase):
    def test_flat_label_has_zero_numeric_prediction(self):
        signal = SimpleNamespace(
            score=0.1,
            name="TEST_SIGNAL",
            confidence=0.5,
            regime="test",
            contradiction=False,
        )
        baseline = SimpleNamespace(score=0.0)
        with patch.object(loop, "combined", return_value=signal), \
             patch.object(loop, "forecast", return_value=baseline), \
             patch.object(loop, "adaptive_ensemble", return_value=(0.0, None, [])):
            result = loop.predict(
                {
                    "EURUSD": [1.1] * 30,
                    "GBPUSD": [1.2] * 30,
                    "USDJPY": [150.0] * 30,
                    "DXY": [100.0] * 30,
                },
                [(1.1, 1.1, 1.1, 1.1)] * 30,
                {"bias": 0.0},
                {"context_score": 0.0, "power_score": 0.0},
            )
        self.assertEqual(result[1], "FLAT")
        self.assertEqual(result[3], 0.0)

    def test_directional_forecast_keeps_signed_return(self):
        signal = SimpleNamespace(
            score=0.8,
            name="TEST_SIGNAL",
            confidence=0.9,
            regime="trend",
            contradiction=False,
        )
        baseline = SimpleNamespace(score=0.0)
        with patch.object(loop, "combined", return_value=signal), \
             patch.object(loop, "forecast", return_value=baseline), \
             patch.object(loop, "adaptive_ensemble", return_value=(0.0, None, [])):
            result = loop.predict(
                {
                    "EURUSD": [1.1] * 30,
                    "GBPUSD": [1.2] * 30,
                    "USDJPY": [150.0] * 30,
                    "DXY": [100.0] * 30,
                },
                [(1.1, 1.1, 1.1, 1.1)] * 30,
                {"bias": 0.0},
                {"context_score": 0.0, "power_score": 0.0},
            )
        self.assertEqual(result[1], "UP")
        self.assertGreater(result[3], 0.0)


if __name__ == "__main__":
    unittest.main()
