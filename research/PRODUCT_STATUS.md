# Product status

## Delivered
- EUR/USD 5-minute forecast engine
- Temporal lock preventing scoring forecasts created after their target window begins
- Forecast record and post-window scoring lifecycle
- Separate trader-consensus aggregation layer
- Sample UTC OHLCV dataset
- Automated pytest CI
- Browser dashboard for manual research forecasts

## Explicitly not claimed
- No broker execution
- No guaranteed prediction accuracy
- No live broker feed in this repository
- No claim of observing private MetaTrader traders
- Sample data is synthetic/research data and is not market ground truth

## Product boundary
This is a research-grade forecasting product. A live deployment requires a licensed/authorized EUR/USD 5-minute market-data feed and a scheduler or streaming adapter. The scoring core is designed so future candles cannot silently enter the prediction snapshot.
