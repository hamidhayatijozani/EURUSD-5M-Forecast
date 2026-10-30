# Multi-provider live market feed

Providers:

1. **OANDA v20** (when configured)
2. **Twelve Data** (when configured)
3. **Yahoo Finance** (no key; research fallback)

Order is controlled by `LIVE_FEED_PROVIDERS`. Secrets are never printed in logs.

## Configure secrets

**Settings → Secrets and variables → Actions**:

- `TWELVEDATA_API_KEY` — Twelve Data key (matches `engine/market_providers.py`)
- `OANDA_API_TOKEN` — optional
- `OANDA_ENVIRONMENT` — `practice` or `live`
- `LIVE_FEED_PROVIDERS` — e.g. `twelvedata,yahoo`

Do not paste tokens into chat, source, or issues.

## Verification state (2026-10-23)

| Provider | Code | Live verification |
|----------|------|-------------------|
| Twelve Data | Yes | **Verified** (288×5m EUR/USD + forecast/Lrzesh) |
| OANDA | Yes | UNKNOWN until secret + log selection |
| Yahoo | Yes | Research fallback |

See `docs/OPERATIONAL_STATUS.md`.


Twelve Data intraday requests explicitly set `timezone=UTC` and `include_ohlc=true`. The parser treats its naive `datetime` strings as UTC only under that pinned request contract; do not remove the timezone parameter without changing the parser and its tests.

## Sanitized provider failure diagnostics

The live loop never prints raw provider exception text, request URLs, or query parameters. It now records a bounded failure code after each failed provider:

- `NOT_CONFIGURED` — the provider credential or symbol is not configured.
- `HTTP_401`, `HTTP_403`, `HTTP_429`, etc. — HTTP status only; response body and URL are omitted.
- `NETWORK_ERROR` / `TIMEOUT` — transport failure.
- `PROVIDER_REJECTED` — provider returned its documented error payload.
- `NO_COMPLETE_CANDLES`, `NO_CLOSED_CANDLES`, `STALE_CANDLES`, `INSUFFICIENT_CONTIGUOUS_CANDLES` — data-quality/freshness rejection.
- `UNCLASSIFIED_VALUE_ERROR` — a value/payload error that needs code-level investigation without exposing the raw message.

A successful workflow with `LIVE_CYCLE_HOLD` is not a successful forecast. It means no new prediction was emitted for that cycle. A live-data pilot requires a recent `LIVE_FEED_PROVIDER_SELECTED` record and a fresh closed candle with provider, timestamp, age, and payload provenance.
