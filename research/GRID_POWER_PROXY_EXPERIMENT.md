# Grid-load proxy experiment: preregistration draft

## Claim
**G-001:** A fresh grid-load anomaly feature, sampled before the forecast timestamp, adds incremental information about EUR/USD five-minute realized volatility or absolute return beyond a time-of-week baseline and market-only baseline.

This is not a claim that grid load predicts EUR/USD direction, or that national electricity demand reveals the load of FX servers.

## Source hierarchy and constraints
- **Great Britain:** NESO Open Data provides national-system datasets, including demand forecasts and measured system data. National demand is not London-specific and is not data-centre load. Dataset frequency and publication lag must be checked per dataset before use. Official portal: https://www.neso.energy/data-portal
- **Germany:** ENTSO-E Transparency Platform provides electricity-system data; API access requires account/token setup. The available series are grid/system measurements, not Frankfurt data-centre power. Official docs: https://transparency.entsoe.eu/api-docs/introduction and token instructions: https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188-How-to-get-security-token
- **United States:** EIA provides hourly electricity operating data and other series; API registration is required. State/grid data is not equivalent to cloud-provider or data-centre consumption. Official API: https://www.eia.gov/opendata/v1/
- **FX activity proxy:** OANDA candle `volume` is the number of prices created during that candle interval, not total global FX traded volume. It is broker/feed-specific and must be labelled accordingly. API docs: https://developer.oanda.com/rest-live-v20/pricing-ep/
- **Direct data-centre observations:** use only if the provider exposes timestamped, region-specific measurements under an accessible licence. Provider marketing material or installed capacity is not live power consumption.

## Feature contract
- Store source, series/dataset identifier, region, unit, source timestamp, retrieval timestamp, and raw payload hash.
- Reject missing timestamps, mixed units/regions, invalid values, and observations later than forecast issue time.
- Reject stale observations; for five-minute forecasts, coarse hourly/daily feeds are likely too stale to help and must not be forward-filled as if live.
- Convert load to a dimensionless anomaly against a preregistered historical baseline. Raw MW must not be added to FX volume.
- The initial implementation emits a bounded **non-directional** anomaly only. It must not cast a buy/sell vote.
- The supplied `grid_load_features` function is a pure feature transform, not a provider connector. It makes no network calls and does not alter the live forecast.

## Evaluation protocol
1. Persist each source observation and its source timestamp before using it.
2. Test whether grid features predict future absolute return/realized volatility and regime changes, not direction first.
3. Compare market-only, time-of-week-only, grid-only, and market+grid models on the exact same forecast timestamps.
4. Use chronological walk-forward splits, purged/embargoed overlapping five-minute targets, friction-aware return metrics, and block-bootstrap intervals.
5. Keep each geography and source separate. No pooling regions without a preregistered rationale.
6. Return `UNAVAILABLE`, `STALE`, or `INSUFFICIENT_DATA` rather than impute unavailable feeds.
7. Kill G-001 if it fails the preregistered out-of-sample criterion. No live trading use until later untouched data confirms incremental value.

## Current status
- Research contract and pure feature transform: added on the research branch.
- Provider API keys, source connectivity, and live ingestion: not configured or verified by this change.
- Live engine integration: not enabled.
- Forecast improvement, direction accuracy, and profitability: unknown.
