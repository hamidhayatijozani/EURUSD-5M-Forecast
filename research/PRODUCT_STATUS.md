# Product status

Implemented in the repository:
- executable EUR/USD 5-minute baseline
- temporal validity lock
- post-window scoring
- independent consensus aggregation
- UTC sample OHLCV data
- browser dashboard
- pytest CI

The repository does not claim live broker execution, guaranteed profitability, private MetaTrader trader-position access, certification, or predictive superiority. The sample candles are synthetic.

A production live mode needs an authorized EUR/USD 5-minute data feed and scheduler/stream adapter. The forecast core must receive only the information available at prediction time.
