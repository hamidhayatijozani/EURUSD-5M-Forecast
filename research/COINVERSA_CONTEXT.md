# Coinversa supplemental context

The optional adapter in `engine/coinversa_context.py` retrieves Coinversa Pulse statistics and the aggregate Hyperliquid risk overview. It is context only: it does **not** supply EUR/USD OHLC candles and does not create a directional EUR/USD signal.

## Configuration

Set `COINVERSAA_API_KEY` in the runtime environment or GitHub Actions Secrets. Do not commit the key. Without a key, Coinversa reports `UNAVAILABLE:NO_API_KEY` and the existing EUR/USD news/trader/power context continues.

The adapter calls:
- `GET https://api.coinversa.ai/api/public/v1/pulse/stats`
- `GET https://api.coinversa.ai/api/public/v1/live/risk/overview`

Each call has a short timeout. Provider errors are converted to explicit unavailable statuses and do not abort the forecast context pipeline. The returned context is marked `directional_signal: false` and `eurusd_ohlc: false`; downstream logic must not treat Hyperliquid metrics as spot-FX candles or as an EUR/USD trading recommendation.

## Verification boundary

This change has not been tested in a live environment as part of this commit. Unit tests are included for missing credentials, successful responses, secret redaction, and non-fatal provider failures. Live API entitlement, GitHub Actions Secret configuration, endpoint availability, and response-schema compatibility remain unverified until CI and a controlled live probe provide evidence.
