# ClaimLab Consensus Evidence Protocol

Status: **PRE-REGISTERED RESEARCH PLAN — NOT YET EXECUTED**
Created against repository main commit `9d79e9273c17b592cd2072c335bcd2537072d89c` on 2026-10-09.
This document does not change the locked registry or claim that predictive edge or profitability has been established.

## 1. Research question

Does the current EUR/USD forecasting system provide reproducible out-of-sample improvement over a zero-return baseline at a five-minute horizon, after temporal validation, dependence-aware uncertainty estimation, multiple-testing correction, and explicit trading-cost sensitivity?

The immediate experiment evaluates the existing historical walk-forward baseline only. New model families and external context are separate follow-up claims and must not be mixed into the primary test after results are seen.

## 2. Consensus evidence informing the protocol

These papers motivate evaluation choices; their results are not evidence about this repository's model.

1. López-Herrera, Francisco; González Maiz Jiménez, Jaime; Reyes Santiago, Adán (2025), *Directional forecasting for eight forex pairs against the US dollar using machine learning techniques*, **Discover Artificial Intelligence**, volume 5, 8 citations in the Consensus record. Consensus record: https://consensus.app/papers/directional-forecasting-for-eight-forex-pairs-against-the-lópez-herrera-jiménez/58769b901b7255b58e226ec67a764fd3/?utm_source=chatgpt. Methodological takeaway: time-series cross-validation, explicit costs, future validation periods, and multiple-testing-aware comparisons.
2. Junior, Michael Ayitey; Appiahene, Peter; Appiah, Obed; Bombie, Christopher Ninfaakang (2023), *Forex market forecasting using machine learning: Systematic Literature Review and meta-analysis*, **Journal of Big Data**, 10, pages 1–40, 68 citations in the Consensus record. Consensus record: https://consensus.app/papers/forex-market-forecasting-using-machine-learning-junior-appiahene/7921ba00f20651e4a1da25b24507650b/?utm_source=chatgpt. Methodological takeaway: compare evaluation designs and metrics, not just model names.
3. Bahammou, Imane; Ziti, S. (2026), *Machine Learning for Financial Market Prediction: A Systematic Literature Review*, **Statistics, Optimization & Information Computing**, 1 citation in the Consensus record. Consensus record: https://consensus.app/papers/machine-learning-for-financial-market-prediction-a-bahammou-ziti/03a4d6d466825e408b3e6e02c61204d4/?utm_source=chatgpt. Methodological takeaway: predictive accuracy does not establish economic viability; cost-aware backtesting and ablation are required. This is a recent, low-citation record and is treated as a warning, not settled consensus.
4. Enkhbayar, Sugarbayar; Ślepaczuk, R. (2025), *Predictive modeling of foreign exchange trading signals using machine learning techniques*, **Expert Systems with Applications**, volume 285, article 127729, 14 citations in the Consensus record. Consensus record: https://consensus.app/papers/predictive-modeling-of-foreign-exchange-trading-signals-enkhbayar-ślepaczuk/f3b90a50a16456fc8bdcc9419403e6e5/?utm_source=chatgpt. Methodological takeaway: compare ML signals with traditional baselines across assets, frequencies, and periods.

## 3. Frozen primary experiment

- Instrument: EUR/USD.
- Horizon: 300 seconds on consecutive, correctly timestamped five-minute bars.
- Current candidate under test: existing `claimlab.walkforward.walk_forward` rolling-mean-return baseline, with its default 12-bar lookback.
- Baseline: zero predicted return.
- Data: the configured real historical EUR/USD five-minute OHLCV source, downloaded as raw text once per run and identified by SHA-256, row count, first/last timestamp, and source URL in the evidence capsule.
- Information cutoff: all feature timestamps must be no later than `issued_at`; the target bar must be strictly later. Gaps are skipped, never silently treated as consecutive five-minute bars.
- No parameter selection on the final evaluation period. If parameters are selected, use an earlier chronological training/validation segment and keep the final segment untouched.
- Dataset snapshot, commit SHA, registry hash, configuration hash, and costs must be recorded with the results.
- The synthetic browser sample is prohibited as evidence for market-performance claims.

## 4. Pre-declared metrics and decision rules

Use the current locked registry as the authority for its existing claims. Do not edit its thresholds after observing results.

| Claim | Metric | Minimum success condition |
|---|---|---|
| C001 | MAE improvement = baseline absolute error minus model absolute error | 95% dependence-aware block-bootstrap CI lower bound > 0, and the claim survives the registry's Benjamini–Hochberg (BH) correction |
| C002 | Directional hit rate | 95% Wilson CI lower bound > 0.50, and the claim survives BH correction |
| C003 | Friction-adjusted return | 95% dependence-aware block-bootstrap CI lower bound > 0, and the claim survives BH correction |
| C004 | Temporal validity rate | Exactly 1.0; any leakage invalidates the run |
| C005 | Duplicate prediction rate | Exactly 0.0 |
| C006 | Evidence ledger integrity | Exactly 1.0 |

Additional data sufficiency rule for this protocol: require at least 100 valid observations **and** effective sample size of at least 100 for a performance verdict. If either condition fails, report `INSUFFICIENT_DATA`, regardless of the point estimate. This is a protocol-level conservative gate; it does not silently rewrite the locked registry's existing `minimum_n` value.

Use 2,000 bootstrap resamples, alpha 0.05, fixed seed 20261006, and the registry's overlap block of five for one-minute-issued, five-minute-horizon forecasts. For the historical five-minute-bar experiment, preserve temporal order and report the dependence treatment explicitly; do not claim that five-bar blocks are universally optimal. Report raw n and effective n separately.

Integrity claims are hard gates, not performance claims. Do not count passing integrity checks as evidence of predictive edge.

## 5. Trading-cost treatment

The current live loop's `FRICTION=0.00002` is a configured assumption, not proof of realistic executable costs. The primary historical result must report the exact cost assumptions. Where executable bid/ask and slippage data are unavailable, publish a cost-sensitivity table rather than a single profitability assertion. At minimum test total round-trip cost assumptions of 0.2, 0.5, and 1.0 pip (EUR/USD: 1 pip = 0.0001), explicitly label them as scenarios rather than observed broker quotes, and keep commission/slippage assumptions visible. A positive result only at the lowest scenario is not enough to claim deployable profitability.

## 6. Follow-up experiments (separate claims; not part of the primary test)

Run one change at a time, with the primary baseline frozen:

- Model family comparison: rolling mean, zero-return, logistic regression, and one tree-based model. Hyperparameters are selected only inside chronological training/validation folds.
- Objective comparison: optimize directional accuracy versus a pre-defined cost-aware objective; do not choose the objective after inspecting final-period returns.
- Regime robustness: classify regimes using past-only volatility thresholds, and report performance and sample size for each regime.
- Ablation: remove one component at a time (cross-asset context, candle-pattern features, external news/power context, adaptive weighting). Report incremental change against the same frozen baseline.
- External context is eligible only when source, timestamp, availability time, missingness, and transformation are recorded. No private top-trader feed may be implied without an authorized, verifiable source.
- Any model or feature search creates a new family of hypotheses; register the full family before testing and correct for multiplicity.

The human-readable feature claims in `CLAIMLAB.md` (external context, top-50 trader context, candle patterns, adaptive weighting) are not the same as the current locked statistical registry's C001–C006 identifiers. Do not reuse those identifiers for different meanings. A future feature experiment must create a new versioned registry and lock it before evaluation.

## 7. Current evidence audit (snapshot inspected 2026-10-09)

Repository main at inspection: `9d79e9273c17b592cd2072c335bcd2537072d89c`.

- `research/claimlab_live_observations.jsonl`: 3 rows marked VALID, spanning issue time 2026-10-07 00:37 UTC through resolution at 00:44 UTC.
- On those 3 rows, mean MAE improvement versus the stored baseline is approximately -0.0000067319 (negative means the candidate's absolute error was worse); mean friction-adjusted return is approximately -0.0000575301; directional hits are 0/3.
- These three observations are far below the preregistered minimum and are not statistically decisive. Do not extrapolate them into a market conclusion.
- `research/live_predictions.jsonl`: 40 records were found: 33 marked RESOLVED, 5 EXCLUDED_PRE_CONTRACT, and 2 PENDING. Only 5 carried `freshness-90s-v1`; 3 of those are represented in the clean observation ledger and 2 remain pending. Legacy rows without the current freshness contract must not be mixed into clean evidence.
- `data/sample_eurusd_5m.csv` contains only 12 rows and is explicitly a synthetic sample; it cannot satisfy the real-market experiment.
- The repository has a real historical-data walk-forward script, but no current evidence capsule from a successful recent run was verified during this inspection. Therefore the full historical experiment remains **NOT YET VERIFIED**.

These are repository snapshot counts, not live market observations as of the current time. The live ledger's latest resolved observation is stale relative to this document's creation date.

## 8. Required run artifact

Each completed run must preserve:

1. Raw dataset SHA-256, source URL, row count, and timestamp range.
2. Code commit, config hash, and locked registry hash.
3. Number of rows skipped for gaps or invalid timestamps.
4. Valid n and effective n.
5. All preregistered metrics, confidence intervals, raw p-values, BH decisions, cost scenarios, and regime-conditioned results.
6. Temporal validity, duplicate rate, and ledger-integrity results.
7. Final verdict: `SURVIVE`, `KILL`, or `INSUFFICIENT_DATA`, with no manual override after results are observed.

## 9. References and tool boundary

Consensus was used to discover and retrieve the paper records listed above. Paper summaries and citation counts are those exposed in the retrieved Consensus records; citation count is not a quality score. No source paper's reported metric is copied into ClaimLab's success threshold. This protocol is a repository change proposal until merged, and the full real-data experiment is not complete until its evidence capsule and run result are inspected.
