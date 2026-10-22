# Twelve Data EUR/USD 5-minute ingestion

## Purpose and status

This adapter is an ingestion/probe path only. A successful provider response does **not** prove predictive edge, trading profitability, or end-to-end ClaimLab settlement.

### Live verification (2026-10-23)

A controlled probe using the multi-provider adapter selected **Twelve Data**, received **288** EUR/USD 5-minute candles, and successfully ran baseline forecast + Lrzesh. See `docs/OPERATIONAL_STATUS.md`.

GitHub Actions still requires the repository secret for CI/scheduled runs.

## Configure the API key safely

1. Open **Settings → Secrets and variables → Actions**:
   https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/settings/secrets/actions
2. Create secret **`TWELVEDATA_API_KEY`** (exact name read by Python code).
3. Optional: `LIVE_FEED_PROVIDERS` = `twelvedata,yahoo`.
4. Never commit the key to source, workflows, or issues.

## Interpreting results

- Unit tests: synthetic only.
- Live probe with fresh closed candles: ingestion path works at probe time.
- Log `LIVE_FEED_PROVIDER_SELECTED` with `"provider":"twelvedata"` confirms source.
- No orders are placed by this path.
