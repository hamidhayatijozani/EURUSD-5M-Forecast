# Operational Status — EURUSD-5M-Forecast

Last update: **2026-10-23** (UTC)

## Verified today

| Component | Status | Evidence |
|-----------|--------|----------|
| Twelve Data EUR/USD 5m feed | **VERIFIED** | Live probe returned 288 closed candles; last close ≈ 1.12218 |
| Multi-provider adapter (`engine/market_providers.py`) | **VERIFIED** | Provider selected: `twelvedata` |
| Baseline forecast engine | **VERIFIED** | Ran on live closes |
| Lrzesh integration | **VERIFIED** | TS computed; regime returned; no future-data leakage |
| GitHub Actions secret wiring | **OWNER ACTION REQUIRED** | Secrets cannot be written by this automation; must be set in repo Settings |

## Sample live cycle (research, not a trade signal)

- Provider: Twelve Data
- Interval: 5min
- Candles: 288
- Direction: FLAT
- Confidence: ~0.73
- Regime: VOLATILE
- Lrzesh TS: ~0.10 → TREND_STABLE
- Iron Condor suggestion: none (TS below threshold)

This is a measurement of the software path. It is **not** a profitability claim.

## Required GitHub Secrets (owner only)

Set under **Settings → Secrets and variables → Actions**:

| Secret name | Purpose |
|-------------|---------|
| `TWELVEDATA_API_KEY` | Twelve Data API key (matches code in `market_providers.py`) |
| `LIVE_FEED_PROVIDERS` | Optional; recommended value: `twelvedata,yahoo` |
| `OANDA_API_TOKEN` | Optional OANDA read-only token |
| `OANDA_ENVIRONMENT` | `practice` (default) or `live` |

**Never commit API keys to source, issues, or workflow logs.**

Note: older docs sometimes wrote `TWELVE_DATA_API_KEY`. The **code** reads `TWELVEDATA_API_KEY`. Use the code name.

## Still not claimed

- Broker order execution
- Guaranteed edge / profitability
- Continuous 24/5 scheduled production without Actions secrets + runner
- OANDA live verification (until its secret is present and selected in logs)

## How to re-verify after secrets are set

1. Add `TWELVEDATA_API_KEY` in GitHub Actions secrets.
2. Run workflow `twelvedata-ingestion.yml` with live probe enabled, or the live research workflow.
3. Confirm log line `LIVE_FEED_PROVIDER_SELECTED` with `"provider": "twelvedata"`.
4. Confirm no key material appears in logs.
