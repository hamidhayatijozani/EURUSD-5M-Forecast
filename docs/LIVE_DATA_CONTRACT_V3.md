# Live data contract v3

## Purpose

Prevent a live forecast from being backdated to a candle close when the process only received the completed candle later. A successful data fetch is not proof that the data was available at the timestamp assigned to the forecast.

## Timestamp semantics

For a one-minute OHLC candle:

- `source_candle_ts` is the candle-open timestamp supplied by the provider.
- `feature_cutoff_at` is the candle close: `source_candle_ts + 60 seconds`.
- `observed_at` is the actual UTC time the process received the completed provider snapshot.
- `prediction_ts` is captured after feature/context calculation, and must be greater than the feature cutoff and no earlier than `observed_at`.
- `data_age_seconds` is frozen at issuance: `prediction_ts - feature_cutoff_at`.
- The live freshness limit is 90 seconds at issuance. If computation pushes the observation beyond that limit, the cycle emits HOLD and does not persist a forecast.

All four timestamps must be timezone-aware. Missing or contradictory provenance is rejected, not defaulted.

## Target contract

The live loop uses one-minute candles to resolve a minimum five-minute forecast horizon:

1. Compute `minimum_target_at = prediction_ts + 300 seconds`.
2. Select the first completed one-minute candle close at or after `minimum_target_at`.
3. Store its candle-open key in `target_ts` and its close timestamp in `target_at`.
4. Store the exact realized `horizon_seconds = target_at - prediction_ts`.

The realized horizon is at least 300 seconds and less than 360 seconds. ClaimLab uses the exact row horizon; overlap-aware inference rounds the maximum realized horizon up to whole minutes.

This live one-minute target contract is distinct from the historical five-minute walk-forward contract. Their observations remain separated by `data_mode`; results must not be pooled without an explicit horizon and provenance analysis.

## Provenance modes

- `LIVE`: complete provider, source, observation, feature-cutoff, issuance, freshness and age evidence.
- `HISTORICAL`: named historical source, source candle timestamp, feature cutoff, and `freshness_status=NOT_APPLICABLE`; no fabricated observation time or live age.
- `UNVERIFIED`: legacy or incomplete provenance. Such records are marked INVALID and excluded from scoring.

The v3 contract quarantines pending live predictions from earlier timing contracts rather than silently rewriting their timestamps.

## Execution boundary

This repository's live research loop is read-only with respect to broker execution. It must not place broker orders, submit trades, or claim profitability from these observations.
