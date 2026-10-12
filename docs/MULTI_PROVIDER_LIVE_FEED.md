# Multi-provider live market feed

The live research loop can use three independent market-data providers:

1. **OANDA v20 candles** (preferred when configured; broker API credentials required).
2. **Twelve Data time series** (fallback when configured; API key required).
3. **Yahoo Finance chart endpoint** (no API key; research-only fallback).

Provider order is controlled by `LIVE_FEED_PROVIDERS`. The GitHub Actions workflow sets
`oanda,twelvedata,yahoo`. A provider without credentials or without a supported symbol is
skipped, and failures fall through to the next provider. Secrets are never printed in logs.

## Configure from GitHub mobile/web

Open the repository, then **Settings → Secrets and variables → Actions → New repository secret**.
Add these only if you have them:

- `OANDA_API_TOKEN`: OANDA personal access token. Start with an OANDA practice account.
- `TWELVEDATA_API_KEY`: Twelve Data API key.

Optional under **Settings → Secrets and variables → Actions → Variables**:

- `OANDA_API_BASE`: omit to use the practice endpoint. For an explicitly authorized live account,
  set `https://api-fxtrade.oanda.com`.
- `OANDA_ENVIRONMENT`: `practice` by default; use `live` only with the intended live account.

Do not paste API tokens into chat, source files, commits, issues, or workflow logs. Use GitHub Actions
repository secrets only. The code does not place orders; it only reads candles for research.

## Evidence rules

- Each fetch emits `LIVE_FEED_PROVIDER_SELECTED` with symbol, provider, interval, and candle count.
- Failover emits provider names and exception types only; no URLs or exception text that could echo keys.
- The actual provider used for EURUSD is saved into each prediction record.
- Existing closed-candle, alignment, freshness, and exact-target settlement checks remain mandatory.
- If all providers fail, the cycle holds and does not emit a new forecast from stale data.
- A successful fetch is not proof of broker-grade quality, profitable forecasts, or execution readiness.
- Yahoo remains research-only. Do not treat it as a trading/execution-grade source.

## Current credential state

Whether OANDA or Twelve Data secrets exist is not readable through this workflow connection.
Until the run logs show either provider selected, those providers must be treated as
`UNKNOWN / NOT YET VERIFIED`. The no-key fallback is Yahoo.
