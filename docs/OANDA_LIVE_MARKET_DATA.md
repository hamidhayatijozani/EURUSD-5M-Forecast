# OANDA EUR/USD live market-data adapter

This adapter adds read-only EUR/USD quote retrieval and price streaming through the OANDA v20 API. It does not place orders.

## Configuration

Set these environment variables in the runtime or secret manager. Never commit the token.

- `OANDA_API_TOKEN`: personal OANDA v20 API token.
- `OANDA_ACCOUNT_ID`: account ID permitted to access pricing.
- `OANDA_ENVIRONMENT`: `practice` by default; `live` selects the live pricing endpoint.

The API requires an eligible OANDA v20 account and token. Availability depends on OANDA's supported division, account, and jurisdiction. Official documentation: https://developer.oanda.com/rest-live-v20/development-guide/ and https://developer.oanda.com/rest-live-v20/pricing-ep/

## One-shot connectivity probe

Run from the repository root after installing requirements:

```bash
python - <<'PY'
import json
from claimlab.oanda_live import OandaLiveClient

client = OandaLiveClient()
print(json.dumps(client.get_latest_quote(), indent=2))
PY
```

A returned quote is an observation from the configured provider, not evidence of predictive edge. Check `freshness_status`; stale quotes are returned with `FAIL` so they cannot silently be treated as fresh.

## Streaming

`OandaLiveClient.stream_quotes()` yields price events and heartbeat records. The caller must implement bounded reconnect/backoff, durable persistence, monitoring, and controlled shutdown. The stream is account-specific and does not guarantee every underlying price update.

## Verification boundary

Unit tests use fake provider responses and are synthetic tests only. They validate parsing and failure handling; they do not prove live connectivity. A live probe requires valid credentials and a reachable provider endpoint. Do not put tokens in logs, commits, issues, or test fixtures.
