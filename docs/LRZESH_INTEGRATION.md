# Lrzesh Integration

## What was added

`engine/lrzesh.py` introduces a pure, leakage-safe **Trembling Score** (TS) and Gray-Zone regime detector.

- **Trembling Score** (0–1): measures how balanced opposing forces are (momentum divergence + realized volatility + optional sentiment divergence).
- **Regimes**: `GRAY_ZONE` (≥0.78), `TRANSITION` (≥0.55), `TREND_STABLE` (<0.35), `NEUTRAL`.
- **Asymmetric Iron Condor suggestion**: only emitted when TS is high; wider put wing to respect typical EUR/USD skew. Pure research suggestion — never executes.

## Integration point

`engine/forecast.py` now accepts:

```python
forecast(closes, use_lrzesh=True, news_sentiment=0.0, trader_sentiment=0.0)
```

When `use_lrzesh=True` (default):
- LrzeshResult is attached to the Forecast object.
- In Gray Zone, directional confidence is deliberately reduced and weak signals may be forced to FLAT.

## Safety / evidence boundary

- No future candles are used.
- No network calls inside `lrzesh.py`.
- No order placement, broker connection, or profitability claim.
- Iron Condor output is a research suggestion only.
- Existing temporal-validity and ClaimLab contracts remain unchanged.

## How to test

```bash
PYTHONPATH=. pytest tests/test_lrzesh.py -q
```

## Status

Research integration complete on branch `feature/lrzesh-integration-v1`.
Live operational use still requires a verified market-data provider and scheduler (already documented in the main README).
