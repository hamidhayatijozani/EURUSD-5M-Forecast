# ClaimLab Cost-Sensitivity Result — 2026-10-09

Status: **COMPUTED — THE CANDIDATE REMAINS KILLED AT ALL THREE COST SCENARIOS**

This follow-up reprices the same frozen historical forecasts from the preregistered walk-forward run. It does not generate new forecasts, change target returns, tune model parameters, or create an independent sample.

## Provenance

- PR: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/12
- Workflow run: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37934521214
- Workflow job: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37934521214/job/113833120349
- Source data SHA-256: `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6`
- Source observations: 37,584 walk-forward forecasts; 2026-03-26 to 2026-09-25 source range.
- Evidence artifact: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/37934521214/artifacts/11617950806
- Artifact ZIP SHA-256: `e2f1fc08f114d1f4bcaf79cd62cf76cda3b36b727e1f5c7f54a172bba1f6724b`
- Full test suite: 54 passed in 0.55 seconds.
- Walk-forward contract tests: 3 passed; historical walk-forward completed successfully.

## Predeclared cost scenarios

EUR/USD pip size is treated as 0.0001 return units. These are sensitivity assumptions, **not observed broker quotes**. Slippage and commission remain zero in this calculation, so the table must not be read as an executable cost model.

| Total round-trip cost assumption | Mean friction-adjusted return | 95% block-bootstrap CI | Directional hit rate | 95% Wilson CI |
|---:|---:|---:|---:|---:|
| 0.2 pip (0.00002) | -0.0000221582 | [-0.0000239873, -0.0000203259] | 0.41563 | [0.41066, 0.42062] |
| 0.5 pip (0.00005) | -0.0000521582 | [-0.0000539873, -0.0000503259] | 0.33578 | [0.33102, 0.34057] |
| 1.0 pip (0.00010) | -0.0001021582 | [-0.0001039873, -0.0001003259] | 0.21512 | [0.21099, 0.21930] |

The model's mean gross return before the cost deduction is approximately -0.0000021582 per observation in this experiment. It is already negative before adding any of these cost scenarios. Increasing costs further reduces net returns and the cost-sensitive directional hit rate.

## Decision

The 12-bar rolling-mean-return candidate remains **KILLED**. Every scenario has a negative mean net return with a confidence interval entirely below zero, and every directional hit-rate interval is below 0.50.

This conclusion applies only to the tested rolling-mean candidate, historical dataset snapshot, target definition, and evaluation procedure. It is not a verdict on the separate live ensemble or on feature hypotheses that were not evaluated here.

## Next research method: control for model-selection overfitting

Before ClaimLab searches many candidate models or parameters, register the complete candidate family and add a model-selection-aware diagnostic. Two relevant Consensus records are:

1. Bailey, David H.; López de Prado, Marcos M. (2014), *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality*, **The Journal of Portfolio Management**, volume 40, 166 citations in the Consensus record. https://consensus.app/papers/the-deflated-sharpe-ratio-correcting-for-selection-bias-bailey-prado/378afd063fd15487a4fcb21af0850767/?utm_source=chatgpt
2. Bailey, David H.; Borwein, J.; López de Prado, Marcos M.; Zhu, Q. (2016), *The probability of back-test over-fitting*, 114 citations in the Consensus record. https://consensus.app/papers/the-probability-of-backtest-overfitting-bailey-borwein/f5ef21e8509b544fba76ccc9aa2de55c/?utm_source=chatgpt

These methods address selection effects that a simple correction across three already-registered metrics does not fully cover when many candidate strategies have been searched. They are a proposal for a later, separately preregistered experiment, not a claim that DSR or PBO has already been implemented in this repository.
