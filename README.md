# EURUSD-5M-Forecast

Research dashboard for EUR/USD 5-minute market-path forecasting and trader-consensus analysis.

## Status

Initial research scaffold. No claim of profitable prediction, broker execution, or predictive superiority.

## Core loop

1. Ingest OHLCV.
2. Freeze a feature snapshot at prediction time.
3. Produce a 5-minute direction/path forecast.
4. Record the forecast before the target window.
5. Observe the target window.
6. Score the forecast against reality.
7. Measure accuracy, calibration and regime dependence.

The anti-self-deception rule is temporal integrity: future candles must never enter a prediction's feature set.
