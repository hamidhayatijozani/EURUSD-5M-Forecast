# ClaimLab Historical Evaluation Result — 2026-10-09

Status: **COMPUTED — PRIMARY CANDIDATE KILLED UNDER THE LOCKED CRITERIA**

This report records the result of the preregistered historical walk-forward run triggered by PR #10. It is separate from, and does not rewrite, the preregistered protocol.

## Run provenance

- Repository: `hamidhayatijozani/EURUSD-5M-Forecast`
- Protocol PR: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/10
- Workflow run: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37933884657
- Workflow job: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37933884657/job/113830996661
- Code commit recorded in capsule: `03eb7603feea1f6ac58ec22f7a13a4ae3ae32864`
- Locked registry: `EURUSD-5M-CORE-001`
- Registry hash: `3cc5cc79c12bc4b5aa02464be18b5461f900aa3f205ef8de4b783df3917554e3`
- Configuration hash: `00ebf95fec8286612625e3de31f3acc0444d1171bb5ad7de7257040507b3d95a`
- Historical source: https://raw.githubusercontent.com/getdata-finance/eurusd-5m-ohlcv-forex-historical-data/main/EURUSD_5m.csv
- Dataset SHA-256: `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6`
- Source rows: 37,948
- Source range: 2026-03-26 02:30 UTC to 2026-09-25 20:55 UTC
- Valid walk-forward observations: 37,584
- Candidate: 12-bar rolling-mean-return predictor
- Baseline: zero predicted return
- Configured friction: `0.00002` return units; slippage and commission were set to zero. This is an experimental assumption, not a verified broker quote.
- Artifact: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37933884657/artifacts/11616814176
- Artifact SHA-256: `890b228b00dba9f9863128b91f800838ec488e78e78401ffe81ac77a6dbdc575`

## Results

| Metric | Observed result | Interpretation |
|---|---:|---|
| Raw n | 37,584 | Exceeds the protocol minimum |
| Effective n | 37,584 | Reported by the current implementation |
| Model MAE | 0.0001320492 | Higher is worse |
| Baseline MAE | 0.0001254450 | Zero-return baseline |
| MAE improvement (baseline error minus model error) | -0.0000066042 | Candidate is worse |
| 95% bootstrap CI for MAE improvement | [-0.0000070606, -0.0000061539] | Entire interval is below zero |
| Directional hit rate | 0.415629 | Below 0.50 |
| 95% Wilson CI for hit rate | [0.410655, 0.420620] | Entire interval is below 0.50 |
| Mean friction-adjusted return | -0.0000221582 | Negative under configured friction |
| 95% bootstrap CI for friction-adjusted return | [-0.0000239873, -0.0000203259] | Entire interval is below zero |
| Temporal validity rate | 1.0 | Passed in this run |
| Duplicate prediction rate | 0.0 | Passed in this run |
| Ledger integrity | 1.0 | Passed in this run |
| Engine verdict | `KILLED` | Performance criteria fail |

The implementation reports BH rejection for the MAE and return null tests because the observed effects differ from zero. That does **not** mean the model improved: the preregistered direction is positive improvement and positive net return, while both observed effects and their confidence intervals are negative. Direction and sign take precedence over a generic “statistically significant” label.

## Regime check

The past-only volatility-regime report is also unfavorable:

- LOW: n=12,870; hit rate 0.3852; MAE improvement -0.0000039129; friction-adjusted return -0.0000237496.
- MEDIUM: n=11,794; hit rate 0.4195; MAE improvement -0.0000054388; friction-adjusted return -0.0000219721.
- HIGH: n=12,870; hit rate 0.4422; MAE improvement -0.0000103696; friction-adjusted return -0.0000207230.

All three regimes show negative MAE improvement and negative friction-adjusted return in this run. This is not a live-market result and does not establish how a different model or different cost model would perform.

## Decision

**KILL the current 12-bar rolling-mean-return candidate for the preregistered performance claim.** Do not tune its lookback against this same evaluation period and then reuse this period as independent evidence.

This does not kill the entire EURUSD-5M-Forecast project, the live ensemble, or the separate C004–C006 feature hypotheses. Those are different claims and have not been evaluated by this specific walk-forward run.

## Remaining work before any trading claim

1. Add a cost-sensitivity evaluation at the preregistered 0.2, 0.5, and 1.0 pip scenarios; current run used only the existing configured friction.
2. Evaluate the live ensemble separately against the same frozen target timestamps and an explicitly defined zero-return/naive baseline.
3. Compare candidate families in chronological folds, with all model/feature searches included in the multiplicity plan.
4. Register a new versioned claim family before testing external context, trader signals, candle-pattern features, or adaptive weighting.
5. Keep the live feed status separate: this artifact uses historical data ending 2026-09-25 and does not prove a fresh live feed or live profitability.

## CI evidence

The walk-forward contract test step passed: **3 tests passed in 0.07 seconds**. The historical walk-forward job completed successfully and uploaded the evidence artifact. A successful workflow means the experiment executed and produced evidence; it does not mean the model passed its performance claim.
