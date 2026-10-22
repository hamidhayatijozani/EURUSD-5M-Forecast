# Operational Status — EURUSD-5M-Forecast

Last update: **2026-10-23** (UTC)

## Verified

| Component | Status | Evidence |
|-----------|--------|----------|
| Twelve Data EUR/USD 5m feed | **VERIFIED** | Live probe returned 288 closed candles; last close ≈ 1.12218 |
| Multi-provider adapter (`engine/market_providers.py`) | **VERIFIED** | Provider selected: `twelvedata` |
| Baseline forecast engine | **VERIFIED** | Ran on live closes |
| Lrzesh integration | **VERIFIED** | TS computed; regime returned; no future-data leakage |
| GitHub Actions secret wiring | **OWNER ACTION REQUIRED** | Must be set in repo Settings → Secrets |

## Sample live cycle (research only — not a trade signal)

- Provider: Twelve Data
- Interval: 5min
- Candles: 288
- Direction: FLAT
- Confidence: ~0.73
- Regime: VOLATILE
- Lrzesh TS: ~0.10 → TREND_STABLE
- Iron Condor suggestion: none (TS below threshold)

This measures the software path. It is **not** a profitability claim.

## Required GitHub Secrets (owner)

Set under **Settings → Secrets and variables → Actions**:

| Secret name | Purpose |
|-------------|---------|
| `TWELVEDATA_API_KEY` | Twelve Data API key (name used by `market_providers.py`) |
| `LIVE_FEED_PROVIDERS` | Optional; recommended: `twelvedata,yahoo` |
| `OANDA_API_TOKEN` | Optional OANDA read-only token |
| `OANDA_ENVIRONMENT` | `practice` (default) or `live` |

**Never commit API keys to source, issues, or workflow logs.**

## Still not claimed

- Broker order execution
- Guaranteed edge / profitability
- Continuous scheduled production without Actions secrets
- OANDA verification until its secret is present and selected in logs
