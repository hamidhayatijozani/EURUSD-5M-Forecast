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
