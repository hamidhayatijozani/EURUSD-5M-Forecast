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


## Grid-load proxy proposal (research-only)

The user-proposed electricity proxy has been translated into a leakage-safe research contract and a pure feature transform:
- `engine/grid_power_proxy.py` rejects future-dated, stale, invalid, and mixed-region/unit observations; it computes a bounded anomaly against prior observations only.
- `tests/test_grid_power_proxy.py` covers lookahead exclusion, freshness, insufficient history, and region isolation.
- `research/GRID_POWER_PROXY_EXPERIMENT.md` defines source limitations and a preregistered test of future absolute return/realized volatility before any directional claim.

Important source distinctions:
- NESO national demand is not London data-centre consumption.
- ENTSO-E series describe grid/system data, not Frankfurt server load; API access requires token setup.
- EIA electricity data are regional/system proxies, not direct cloud-provider power usage; API registration is required.
- OANDA candle volume is a broker/feed-specific count of prices created in the interval, not total global FX traded volume.

This commit adds **no provider connector**, stores no new live data, changes no live forecast path, and does not establish predictive value. Data ingestion and out-of-sample validation remain pending.


## Latest CI verification (2026-10-12 04:11 UTC)

For head `18f25a0db7de48cc6e6d48c3b0920ebb5eddfff8`:
- Python test workflow: **114 passed in 1.33s**.
- Offline evidence-ablation workflow: **success**, machine-readable artifact uploaded (SHA-256 `b27b83819888a04c8b63b26981dd06315303ea90fd528fedbe1f3ec59a12000f`).
- Test run: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38202781644
- Ablation run: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38202781564
- Artifact: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38202781564/artifacts/11725138834

These checks establish that the repository tests and offline evaluator execute successfully on this commit. They do not establish live provider connectivity, live-market prediction accuracy, or trading profitability. Workflow logs also contain upstream Node.js 20 deprecation warnings for GitHub Actions; they did not fail either run.


## Immutable decision evidence: implementation and exact-head verification

### Implemented on the research branch
- `engine/forecast_evidence.py` snapshots the aligned candle-close series, OHLC rows, feature cutoff, model component outputs, external context, and config hash at forecast issue time.
- The snapshot is canonical-JSON SHA-256 hashed. Verification rejects modified content; the prediction row stores both the snapshot and its hash reference.
- `scripts/live_minute_loop.py` adds the snapshot to each newly emitted prediction and validates snapshot integrity while merging concurrent prediction evidence.
- `scripts/audit_decision_evidence.py` audits persisted resolved rows. It deliberately does not reconstruct historical snapshots from post-outcome records or current model code.
- Regression tests cover future/misaligned timestamps, mismatched lengths, tuple-shaped OHLC, hash tampering, and the actual forecast-cycle fixture emitting a verifiable snapshot.
- The evidence-ablation workflow uploads the existing offline comparison and the decision-evidence audit JSON; audit JSON is also printed to CI logs.

### Current ledger audit result
On the checked-in ledger observed in GitHub Actions:
- Resolved historical predictions: **63**
- Historical rows containing immutable decision snapshots: **0**
- Rows with invalid snapshot hashes: **0**
- Audit status: **INSUFFICIENT_DATA**

This is not a data-integrity pass for the historical rows; it means there are no snapshots to validate. Component-level ablation is not valid for those historical forecasts. The new code can create the needed evidence only for forecasts emitted by this code path.

### Exact-head CI
Commit: `cfe19e7ee1ca0846d1ac0a3d7f4e03e7763eeff1`
- Python tests: **123 passed in 1.40s** — https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38203553355
- Offline ablation plus decision-evidence audit: **success** — https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38203553350
- Machine-readable artifact SHA-256: `19eb0c74595163e59e5482d63804d545360e5a533c91ce79c0f96e8eb2239bd1`

### Remaining release gate
The PR remains draft and is not merged. The live-minute workflow runs from `main` on a five-minute schedule and writes evidence to the main branch. Dispatching the feature branch's live workflow would be unsafe because its persistence code can push its checked-out HEAD to `main`; therefore no live run was dispatched from this draft branch. The next valid proof is: merge through the repository's intended review path, then inspect a scheduled run on the resulting main SHA and verify that a newly issued forecast persists a valid snapshot. Provider connectivity, predictive value, and profitability remain unproven.
