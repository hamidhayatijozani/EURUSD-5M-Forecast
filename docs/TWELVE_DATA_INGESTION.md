# Twelve Data EUR/USD 5-minute ingestion

## Purpose and status

This adapter is an ingestion/probe path only. A successful provider response does **not** prove predictive edge, trading profitability, or end-to-end ClaimLab settlement. The automated unit tests use synthetic fixtures and do not contact Twelve Data.

### Live verification (2026-10-23)

An external controlled probe using the project’s multi-provider adapter selected **Twelve Data**, received **288** EUR/USD 5-minute candles, and successfully ran the baseline forecast + Lrzesh path on those closes. See `docs/OPERATIONAL_STATUS.md`.

GitHub Actions still requires the repository secret to be present for CI/scheduled runs.

## Configure the API key safely

1. In the repository, open **Settings → Secrets and variables → Actions**:
   https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/settings/secrets/actions
2. Create a repository Actions secret named **`TWELVEDATA_API_KEY`** (this is the name the Python code reads).
3. Optional: set variable or secret `LIVE_FEED_PROVIDERS` to `twelvedata,yahoo`.
4. Never commit the key to source code, workflow files, evidence artifacts, or issues. If a key has been pasted into a chat or another log, rotate it with the provider when practical.

## Run the checks

The pull-request workflow installs `requirements.txt`, runs the adapter's synthetic unit tests, then runs the full test suite.

For a real provider probe, open:
https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/workflows/twelvedata-ingestion.yml

Choose **Run workflow** and set `run_live_probe` to `true` when available. This requires the repository secret above. The probe requests EUR/USD 5-minute candles, rejects candles that are not yet closed, and writes sanitized metadata to a workflow artifact. The artifact is evidence of ingestion only, not of a valid forecast edge or successful settlement.

## Interpreting results

- Unit tests passing: adapter behavior passed synthetic tests only.
- Live probe passing with fresh closed candles: ingestion path works at probe time.
- Missing key, provider error, rate limit, stale data, or no completed candle: ingestion is not verified.
- Log line `LIVE_FEED_PROVIDER_SELECTED` with `"provider":"twelvedata"` confirms which source was used.

The current path does not place orders. `LIVE_SETTLEMENT` and `PREDICTIVE_EDGE` remain unverified until separately demonstrated with timestamped, auditable evidence.
