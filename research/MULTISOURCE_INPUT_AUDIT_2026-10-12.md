# Multi-Source Input Audit — 2026-10-12

## Scope and evidence boundary

Read-only audit of the default branch snapshot at commit `749d84a6a12240e55fd13a84b6a93918f1abcc8c`. This document records repository evidence, not a claim that the live feed or any external service is currently reachable.

Files inspected:
- `engine/context.py`
- `engine/algorithm_factory.py`
- `engine/experiments.py`
- `engine/live_feed.py`
- `scripts/live_minute_loop.py`
- `research/live_state.json`
- `research/live_predictions.jsonl`
- `research/cross_asset_live_observations.jsonl`
- `tests/test_context.py`
- `CLAIMLAB.md`

## Observed facts

### Current-contract EUR/USD ledger

The checked-in `research/live_predictions.jsonl` contains 74 rows:
- 30 resolved rows with `data_contract_version=freshness-90s-v2`
- 4 pending rows with that contract
- 7 rows marked `EXCLUDED_PRE_CONTRACT`
- the remaining rows are older resolved records

For the 30 resolved current-contract observations, the stored `hit` flag is 11/30 (36.7%), consistent with `research/live_state.json`. This metric tests the sign of `predicted_return` against the realized return, counting a hit only when the realized move exceeds the configured friction threshold (0.00002 in return units). It is not the same as direction-label accuracy because a row can have direction `FLAT` while its continuous predicted return is non-zero.

On the same 30 observations, naively negating `predicted_return` gives 9/30 hits (30.0%) under that friction-aware metric. Ten observations have realized absolute return at or below friction, so they are neither wins for the original signal nor wins for its inverse. This is a retrospective in-sample diagnostic, not an independent test and not a deployable strategy result. The inverse hypothesis must be preregistered and tested on later untouched observations.

### External context availability

The checked-in recent rows show:
- GDELT news: `UNAVAILABLE:URLError`
- trader signal file: `NO_SIGNAL_FILE`
- Electricity Maps power proxy: `UNAVAILABLE:NO_API_KEY`

The last persisted `last_external_context` also reports `context_coverage=0.0` and `context_degraded=true`. Thus the code path exists, but these persisted observations do not demonstrate incremental value from those external sources.

### How context enters the forecast

In `scripts/live_minute_loop.py::predict`:
- The main score is `0.55 * base.score + 0.45 * algo_score + 0.18 * context_score + state.bias`.
- If `abs(power_score) >= 0.60`, the whole score is multiplied by 0.80.
- The power proxy is therefore a regime dampener, not a directional vote.
- News and trader score are combined by `fuse_context` with weights 0.55 and 0.45.

In `engine/context.py`:
- News score is the average of article `tone` values after scaling and clipping. It is not yet a validated EUR/USD-specific event surprise or price-response feature.
- Trader ranking is based on error of `predicted_return`, not a direct direction hit rate, and needs a populated, validated `research/trader_signals.jsonl` file plus target-price resolution.
- The declared sources tuple lists all three sources even when they are unavailable; consumers must use the status fields, not the source names, to establish availability.

### Algorithm factory

`engine/algorithm_factory.py` creates 10 candidates: four momentum horizons, three mean-reversion horizons, breakout, candle structure and volatility regime. The ensemble weights candidates by inverse exponentially smoothed MAE.

Risks requiring explicit tests:
- Candidate scores are not obviously calibrated to a common scale: normalized returns, normalized price-to-mean distances, candle score and volatility-regime score are averaged as if comparable.
- The inverse-MAE weight has no explicit minimum sample-size/shrinkage term; new candidates start with the same default MAE and can receive material weight before enough resolved observations accumulate.
- `update_algorithm_stats` learns error for each candidate's predicted return, but this does not prove the candidate contributes incremental direction or net-return value to the ensemble.

### Cross-asset evidence

The checked-in cross-asset ledger contains 54 candidate observations across two contracts, but the candidate-specific samples are small. In contract v2, examples include only three observations each for GBPUSD momentum and inverse USDJPY. These records are useful plumbing evidence, not enough to establish a stable edge. The v2 path intentionally works without DXY, while the v1 path can be partial when DXY is missing.

## Priority findings

1. **No demonstrated external-source contribution:** persisted context is degraded and zero-coverage in the latest saved state.
2. **The inversion story is not supported by current data:** the friction-aware current-contract diagnostic is 11/30 for the original return sign and 9/30 for its inverse, with 10 no-move/under-friction observations. Do not claim 90% or even a 63.3% inverse hit rate from this metric.
3. **Direction, forecast error and trading return are mixed:** report separate metrics for direction (with an explicit FLAT policy), MAE, and friction-adjusted return.
4. **Ablation needs a common timestamp cohort:** baseline, algorithm factory, PST, context, cross-asset, full ensemble and inverse candidate must be scored on exactly the same resolved timestamps; unavailable inputs must be recorded as missing, not silently converted into evidence of zero directional effect.
5. **Overlapping 5-minute targets:** consecutive minute forecasts share most of their horizon. Confidence intervals and significance tests must account for serial dependence, for example via block bootstrap, and the evaluation window must remain untouched by tuning.

## First offline ablation snapshot

The new evaluator was run by GitHub Actions against the checked-in ledgers. The run completed successfully and uploaded a machine-readable artifact. On the 30-row current-contract cohort:

| Candidate | n | Active | Hit rate over all rows | Net return sum | Mean net return per forecast | 95% block-bootstrap CI for mean net return |
|---|---:|---:|---:|---:|---:|---|
| Simple baseline | 30 | 26 | 36.7% | +0.0001530 | +0.00000510 | [-0.0000323, +0.0000405] |
| Full ensemble | 30 | 30 | 36.7% | -0.0000391 | -0.00000130 | [-0.0000312, +0.0000473] |
| Inverse full ensemble | 30 | 30 | 30.0% | -0.0011609 | -0.0000387 | [-0.0000873, -0.00000878] |
| Inverse baseline | 30 | 26 | 20.0% | -0.0011930 | -0.0000398 | [-0.0000747, -0.00000104] |
| MOM_10 candidate | 30 | 26 | 40.0% | +0.0006017 | +0.0000201 | [-0.0000197, +0.0000755] |
| MOM_20 candidate | 30 | 26 | 40.0% | +0.0003773 | +0.0000126 | [-0.0000384, +0.0000755] |

Returns are in decimal return units, with 0.00002 friction per active observation. The confidence intervals are exploratory block-bootstrap intervals on the per-forecast net return series, including zero return for abstentions. Forecast horizons overlap, and the sample is small; do not treat these results as proof of a durable edge. In particular, the simple baseline beats the full ensemble on the observed net-return sum, while the inverse candidate performs worse. This is a reason to test, not a reason to deploy.

External context remained `UNAVAILABLE_NO_DIRECTIONAL_CONTEXT` for all 30 observations in this cohort. Cross-asset candidates such as `LIVE1M2_GBPUSD_MOMENTUM_3M` have only 3 observations and are explicitly marked `INSUFFICIENT_DATA`. The volatility-regime candidate generated no active positions and is marked `NO_ACTIVE_SIGNALS`.

GitHub Actions evidence:
- Offline evaluator: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38202426141
- Artifact: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38202426141/artifacts/11725269555

## Next implementation step

The evaluator exposes a data-contract limitation: per-forecast PST/base component score, algorithm ensemble score/weights at issue time, and raw timestamped context features are not all persisted independently. The next code change should extend forecast evidence to record these components without recomputing them after the outcome is known. Then run common-cohort leave-one-source-out ablations on a later untouched window.

No model weights should be tuned against this same evaluation window. This audit changes no live strategy and authorizes no live trading.
