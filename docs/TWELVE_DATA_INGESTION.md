# Twelve Data EUR/USD 5-minute ingestion

## Purpose and status

This adapter is an ingestion/probe path only. A successful provider response does **not** prove predictive edge, trading profitability, or end-to-end ClaimLab settlement. The automated unit tests use synthetic fixtures and do not contact Twelve Data.

## Configure the API key safely

1. In the repository, open **Settings → Secrets and variables → Actions**:
   https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/settings/secrets/actions
2. Create a repository Actions secret named `TWELVE_DATA_API_KEY` and paste the key there.
3. Never commit the key to source code, workflow files, evidence artifacts, or issues. If a key has been pasted into a chat or another public/private log, rotate it with the provider before relying on it.

## Run the checks

The pull-request workflow installs `requirements.txt`, runs the adapter's synthetic unit tests, then runs the full test suite.

For a real provider probe, open:
https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/workflows/twelvedata-ingestion.yml

Choose **Run workflow** and set `run_live_probe` to `true`. This requires the repository secret above. The probe requests EUR/USD 5-minute candles, rejects candles that are not yet closed, and writes sanitized metadata to the workflow artifact `twelvedata-market-ingestion-evidence`. The artifact is evidence of ingestion only, not of a valid forecast or successful settlement.

## Interpreting results

- Unit tests passing: adapter behavior passed synthetic tests only.
- Live probe passing with `FRESH`: one completed candle was returned within the configured freshness threshold at probe time.
- Missing key, provider error, rate limit, stale data, or no completed candle: ingestion is not verified; inspect the sanitized artifact and provider account limits without exposing credentials.
- No evidence artifact or no successful workflow run: live ingestion remains `UNKNOWN`.

The current probe does not issue forecasts, write settlement outcomes, or establish `LIVE_SETTLEMENT` or `PREDICTIVE_EDGE`. Those remain unverified until separately demonstrated with timestamped, auditable evidence.
