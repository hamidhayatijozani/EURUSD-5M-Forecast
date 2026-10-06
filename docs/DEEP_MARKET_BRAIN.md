# Deep Market Brain

The live engine is now a layered hypothesis machine rather than a single formula.

## Layer 1: raw market

Every forecast starts from the latest common closed one-minute candle for EURUSD,
GBPUSD, USDJPY and DXY. EURUSD additionally supplies OHLC candles.

## Layer 2: candle microscope

engine/patterns.py extracts body, upper/lower wick, range, close position and
multi-scale structure. It evaluates hammer/shooting-star geometry, bullish/bearish
engulfing, inside/outside bars, three-candle directional pressure, range
expansion/compression, and 1/3/8-candle structure.

## Layer 3: algorithm factory

engine/algorithm_factory.py generates independent candidate families: momentum at
multiple horizons, mean reversion at multiple horizons, breakout, candle structure,
and volatility regime. Candidates are combined using error-adaptive weights. Each
candidate is scored against the same future target after that target closes. Its MAE
and bias are updated online.

## Layer 4: external intelligence

News, observed 24h trader error leaderboard, and data-center electricity stress are
fused under the existing information lock.

## Layer 5: reality

Every minute:

forecast(t -> t+5) -> immutable record -> wait -> actual -> error -> candidate learning -> next forecast

Code passing tests is not market success. Survival requires beating the baseline on
independent, friction-adjusted, real-market windows.
