# Cross-Repository Feature Transfer v1 — Preregistered Plan

Status: **PREREGISTERED PLAN — EXPERIMENT NOT YET RUN**

Created before implementation of the candidate feature module. This plan does not alter the locked ClaimLab registry or reuse C001–C006 with new meanings.

## Research question

Do a small, deterministic feature family inspired by the P/S/T vocabulary in HamidCognitionEngine and the hypothesis/ablation discipline in BESAZ add out-of-sample predictive value to EUR/USD five-minute forecasts, beyond a simple baseline, after realistic cost sensitivity?

The source concepts are transferred as measurable market descriptors only. They are not treated as validated cognitive mechanisms, causal explanations, or trading signals.

## Candidate features (v1)

Computed from closed EUR/USD close prices only:

- **pressure**: signed three-bar return normalized by the mean absolute one-bar return in the preceding window.
- **novelty**: absolute latest one-bar return divided by the mean absolute one-bar return of earlier bars in the window.
- **tenacity**: fraction of non-zero one-bar returns that agree with the dominant direction over the window; bounded [0, 1] and measures directional consistency, not psychological persistence.
- **realized_volatility**: root-mean-square one-bar return over the window.
- **trend_efficiency**: absolute cumulative return divided by the sum of absolute one-bar returns; an interpretable path-efficiency diagnostic, not an independent claim.

Zero denominators, non-finite values, non-positive prices, or insufficient observations must fail closed with a clear exception. Feature computation must not fetch data or infer timestamps. Callers must pass only closed candles available at forecast issuance time.

## Experimental controls

1. Do not change the locked core registry, its hash, thresholds, or historical evaluation report.
2. Do not tune on the already evaluated historical period and reuse that period as out-of-sample evidence.
3. Register a separate feature-family claim/registry before any performance evaluation; record code SHA, dataset SHA-256, configuration, issue/target timestamps, costs, and feature version.
4. Compare against the same-window zero-return and existing baseline using chronological walk-forward evaluation.
5. Run ablations: baseline only, each feature family independently, then a limited preregistered combined model. Do not select features on the final holdout.
6. Report MAE improvement, directional accuracy with uncertainty, friction-adjusted return, effective sample size, temporal validity, duplicates, and cost sensitivity. Apply dependence-aware uncertainty and multiple-testing correction.
7. Require at least 100 valid observations and effective sample size >=100 for a performance verdict, following the existing research protocol. Otherwise report INSUFFICIENT_DATA.
8. A statistically significant negative effect is a failure, not a win. No profitability or live-readiness claim is permitted from unit tests or synthetic data.

## Kill criteria

Kill the candidate for the preregistered performance claim if the untouched out-of-sample interval does not support positive improvement after costs, temporal leakage occurs, provenance cannot be reproduced, or the result fails the locked multiplicity-aware criteria. Keep code correctness separate from predictive merit.

## Source lineage and limitations

- HamidCognitionEngine P/S/T: historical simulation lineage; conceptual inspiration only.
- HamidCognition-Unified BESAZ innovation engine: hypothesis/experiment discipline; not evidence of market edge.
- Epistemic Filter: provenance/scope warnings may inspire data-quality checks, but its heuristic VALID verdict is not proof of truth.
- Existing EURUSD engine/trader_sources.py source snapshots record fetch status and byte counts, not extracted, timestamped trader predictions or proven trader skill. They are not inputs to this feature module.

## Current status

Implementation and tests are proposed on branch experiment/cross-repo-features-v1. At this point no feature performance result exists. CI must run before code correctness can be reported as verified.
