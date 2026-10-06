# EURUSD-5M-Forecast

Research-grade EUR/USD 5-minute forecasting and forecast-verification dashboard.

## What this is
A transparent research product that freezes the information set at forecast creation, predicts the next 5-minute direction, records the prediction before the target window, then scores it against observed reality.

Flow:
1. ingest timestamped OHLCV
2. freeze information available at prediction time
3. forecast UP / DOWN / FLAT
4. record target window
5. observe the target window
6. score the forecast

The core rule is temporal: future candles must never be used to create a past forecast.

## Current boundary
Included:
- executable Python baseline engine
- temporal validity lock
- post-window scoring
- independent signal consensus aggregation
- frozen external context fusion: news, 24h top-50 observed trader error, and data-center electricity stress
- JSON forecast schema
- UTC sample dataset
- browser dashboard
- pytest CI

Not claimed:
- guaranteed profitability
- live broker execution
- private MetaTrader trader-position access
- certification
- predictive superiority
- private trader access or a guaranteed 50-trader feed when no licensed/public signal source is configured
- data-center electricity coverage when the external provider/API is unavailable

The sample dataset is synthetic.

## Run
Requires Python 3.12+.

```bash
python -m pip install pytest
PYTHONPATH=. pytest -q
```

Open `dashboard/index.html` in a browser for the visual research dashboard.

For live deployment, connect an authorized EUR/USD 5-minute market-data source and a scheduler/stream adapter. Never inject future candles into the forecast input.

## Verification
CI validates the forecast engine, temporal lock, consensus, and live-feed timestamp filtering.
