# EURUSD-5M-Forecast

Research-grade EUR/USD 5-minute forecasting and forecast-verification dashboard.

## What this is
A transparent research product that freezes the information set at forecast creation, predicts the next 5-minute direction, records the prediction before the target window, then scores it against observed reality.

Flow:
1. ingest timestamped OHLCV
2. freeze information available at prediction time
3. forecast UP / DOWN / FLAT
4. record target window
5. observe the target window
6. score the forecast

The core rule is temporal: future candles must never be used to create a past forecast.

## Current boundary
Included:
- executable Python baseline engine
- temporal validity lock
- post-window scoring
- independent signal consensus aggregation
- frozen external context fusion: news, 24h top-50 observed trader error, and data-center electricity stress
- JSON forecast schema
- UTC sample dataset
- reproducible real EUR/USD 5-minute historical ingestion probe via `claimlab/ingestion.py`
- overlap-aware Effective-N, block bootstrap confidence intervals, Wilson intervals, and Benjamini-Hochberg correction
- cryptographically locked ClaimLab registry and evidence artifacts from GitHub Actions
- browser dashboard
- pytest CI

Not claimed:
- guaranteed profitability
- live broker execution
- private MetaTrader trader-position access
- certification
- predictive superiority
- private trader access or a guaranteed 50-trader feed when no licensed/public signal source is configured
- data-center electricity coverage when the external provider/API is unavailable

The browser dashboard still uses synthetic values for its interactive demo. The ClaimLab ingestion path separately consumes and validates real historical EUR/USD 5-minute OHLCV data. No live-feed claim is made unless a live provider is explicitly configured and its probe succeeds.

## Research protocol
The Consensus-informed, pre-registered research protocol is in [research/CONSENSUS_CLAIMLAB_PROTOCOL.md](research/CONSENSUS_CLAIMLAB_PROTOCOL.md). The first real historical evaluation result is recorded in [research/results/CONSENSUS_CLAIMLAB_EVALUATION_2026-10-09.md](research/results/CONSENSUS_CLAIMLAB_EVALUATION_2026-10-09.md): the tested 12-bar rolling-mean candidate was killed under the locked performance criteria. This is not a verdict on the separate live ensemble or all feature hypotheses. The predeclared cost-sensitivity result is recorded in [research/results/CONSENSUS_CLAIMLAB_COST_SENSITIVITY_2026-10-09.md](research/results/CONSENSUS_CLAIMLAB_COST_SENSITIVITY_2026-10-09.md); the candidate remains killed across all three cost scenarios.

## Run
Requires Python 3.12+.

```bash
python -m pip install pytest
PYTHONPATH=. pytest -q
```

Open `dashboard/index.html` in a browser for the visual research dashboard.

For live deployment, connect an authorized EUR/USD 5-minute market-data source and a scheduler/stream adapter. Never inject future candles into the forecast input.

## Verification
CI validates the forecast engine, temporal lock, consensus, and live-feed timestamp filtering.


## Optional Coinversa market context

Coinversa is an optional **on-chain crypto / Hyperliquid context source**, not an
EUR/USD spot feed and not a source of EUR/USD candles. The adapter in
`engine/coinversa_context.py` calls only the read-only pulse stats endpoint and
keeps the response opaque; it does not infer EUR/USD direction or inject
Coinversa data into OHLCV.

It is disabled by default. To enable the optional fetch in a deployment, set
`COINVERSA_CONTEXT_ENABLED=true` and add `COINVERSAA_API_KEY` as a secret in
the deployment environment (never commit the key). The caller receives
`DISABLED`, `UNAVAILABLE:...`, or `OK` metadata. Provider errors are
contained and must not stop the EUR/USD feed or forecast pipeline. The adapter
is not yet wired into the forecast scoring/fusion path; schema review and
evidence-backed evaluation are required before using any field as a model
feature. No live API call or test execution is claimed by this change.
