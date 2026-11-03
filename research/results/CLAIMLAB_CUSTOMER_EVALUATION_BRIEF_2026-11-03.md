# EURUSD-5M Forecast — Customer Evaluation Brief

**Evidence cut-off:** 2026-11-03 06:00:06 UTC  
**Main at cut-off:** `49c0263d8748930dad81f59e6604b40f85681652`  
**Latest tested code SHA:** `003c3300cbc7cbdd5422d705d1373d928b64d6d5`  
**Product posture:** auditable research/evaluation software, not a proven trading strategy  
**Decision:** **NO-GO for a live-data predictive-performance pilot; GO for a scoped methodology review using frozen historical evidence and the local synthetic UI.**

## Executive decision

A 2026-11-03 live-minute run successfully obtained fresh 1-minute candles from Twelve Data for EURUSD, GBPUSD and USDJPY. It emitted four 5-minute-horizon forecasts, all FLAT and still PENDING when the run ended. This is a useful provider-recovery observation, but it is not a resolved forward-performance sample and it does not establish a sustained feed.

The separate 5-minute market probe reads a static historical GitHub dataset. Its latest candle was dated 2026-09-25 and was correctly classified as stale. A fresh live 5-minute EUR/USD candle has therefore **not** yet been evidenced.

The frozen historical rolling-mean candidate remains **KILLED**; the preregistered candidate arena has zero survivors; the forward paper ledger remains negative after declared costs. No predictive-edge or profitability claim is permitted.

## Evidence table

| Evidence | Result | Interpretation |
|---|---|---|
| Research tests | 184 passed — [run 41586801768](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801768) | Code/test integrity for the tested SHA only |
| Historical ClaimLab | [run 41586801769](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801769), verdict KILLED | Reproducible negative result |
| Historical 5m source probe | [run 41586801888](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801888) | Static dataset reachable; last candle 2026-09-25 20:55 UTC, age 3,315,703s vs 900s limit |
| Live-minute provider run | [run 41586801772](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801772) | Twelve Data supplied 120 closed 1m candles per symbol for EURUSD, GBPUSD and USDJPY; OANDA was not configured |
| Four live forecasts | FLAT/PENDING; data ages 60.8s, 47.9s, 36.2s and 64.6s vs 90s limit | Fresh 1m inputs; no outcome resolved by run end |
| Cross-asset | v2 status READY, but `cross_asset_enabled=false` | Not used in the actual forecast |
| External context | Coverage 0 | News unavailable, electricity API key absent, no trader signal file |
| Paper account | 208 trades; 69 wins / 139 losses; 33.17% win rate | Negative after assumed costs; paper-only |

## Historical ClaimLab result

Source: [historical walk-forward run 41586801769](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801769), [evidence artifact](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801769/artifacts/13208940122).

- Dataset: 37,948 rows; 37,584 valid sequential observations.
- Dataset SHA-256: `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6`.
- Baseline: zero predicted return.
- Candidate: 12-bar rolling-mean-return predictor.
- Baseline MAE: 0.0001254450.
- Candidate MAE: 0.0001320492, worse than baseline.
- MAE improvement: -0.0000066042; 95% block-bootstrap CI `[-0.0000070606, -0.0000061539]`.
- Directional hit rate: 0.415629.
- Net mean return at the declared 0.2-pip spread-only scenario: -0.0000221582; 95% CI `[-0.0000239873, -0.0000203259]`.
- Verdict: **KILLED**.

The nine-candidate preregistered arena previously had zero survivors on its separate 6,529-observation post-cutoff OOS interval. That OOS interval must not be reused for tuning and then presented as independent evidence.

## Live-minute evidence and limits

Source: [live-minute-research run 41586801772](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801772), [diagnostics artifact](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41586801772/artifacts/13208436754).

- Provider: Twelve Data for EURUSD, GBPUSD and USDJPY; 120 closed 1-minute candles per symbol.
- OANDA: `NOT_CONFIGURED`.
- Four forecasts were FLAT, predicted return 0, and PENDING at the end of the run.
- The target horizon was approximately 5 minutes, but the input features came from 1-minute candles. This is not a fresh 5-minute OHLC provider observation.
- All four input ages were below the 90-second freshness limit, but a single run does not establish sustained provider reliability.
- Cross-asset v2 was READY but disabled. External-context coverage was zero.
- No live forecast outcome had resolved by the persisted state snapshot.

A read-only 5-minute Twelve Data adapter and probe script exist. A manual-only workflow is being added so an operator can capture a 5-minute candle with a strict 360-second freshness bound, UTC candle-open/close times, observation time, code SHA and selected-candle-row hash without adding recurring API usage. Until that workflow is run successfully across repeated observations, live 5-minute feed readiness remains unverified.

## Forward-paper result

The 2026-11-03 paper-account evaluation used 423 input rows:

- 282 eligible resolved predictions;
- 34 missing/invalid-evidence rows;
- 63 unresolved rows;
- 44 wrong/missing-contract rows;
- 208 paper trades: 69 wins and 139 losses (33.17% win rate).

Net PnL on a 10,000 starting balance:

| Declared round-trip cost | Net PnL |
|---:|---:|
| 0.2 pip | -8.34 |
| 0.5 pip | -20.80 |
| 1.0 pip | -41.54 |

These are assumed scenarios, not executable broker quotes. Commission is not priced because no broker/venue commission schedule was supplied. The evaluator recorded `profitability_claim_allowed=false`. No broker credentials or order endpoints were used; no real orders were placed.

## Local demo and hosted demo

- Local UI: `dashboard/index.html`. Interactive example values are synthetic and demonstrate interface/workflow only.
- Hosted demo: **BLOCKED**; no public hosted demo is claimed.
- Methodology and operating limits: [ClaimLab methodology](../../CLAIMLAB.md) and [Operational Status](../../docs/OPERATIONAL_STATUS.md).

## Proposed methodology-review pilot

**Proposed fee: US$2,500 for 30 days.** This is a proposal, not a validated market price, signed quote, contract, customer, payment or revenue record.

### Included
- One customer team, one instrument (EUR/USD), one agreed 5-minute research horizon.
- Read-only research and evidence review.
- Frozen historical report, source/provenance audit, temporal-contract review, zero-return baseline, and declared spread/slippage sensitivity.
- Reproduction of the ClaimLab verdict and preservation of failed hypotheses.
- Weekly evidence summary and final methodology report.

### Excluded
- Broker credentials, account access, customer funds, live order placement or automated execution.
- Guaranteed returns, investment advice, predictive superiority or profitability claims.
- A promise of OANDA availability, sustained Twelve Data availability, or external-context coverage that has not been evidenced.
- Reuse of the killed candidate's OOS interval for tuning.

### Start gates for any live-data predictive evaluation
1. Run the dedicated read-only 5-minute Twelve Data probe and retain a fresh completed candle with provider, symbol, UTC candle-open/close, observation time, age, freshness threshold, code commit and candle-row hash.
2. Repeat the probe across multiple distinct 5-minute intervals; a single success is not sustained availability.
3. Preserve a fresh closed-candle feature snapshot and exact target window for every forecast; future inputs must remain excluded.
4. Obtain customer-approved executable spread, slippage and commission inputs. Scenario costs are not broker quotes.
5. Freeze a new hypothesis, feature set, thresholds, cost assumptions and multiplicity plan before any new untouched OOS test.
6. Require at least 1,000 resolved forward observations for an edge claim, plus the preregistered minimum trade count and statistical survival after realistic costs. No candidate may be promoted from insufficient data.

### Acceptance criteria for the methodology review

Acceptance concerns reproducibility and transparent limitations, not profit:
- Reproduce the frozen historical report from dataset hash, locked registry, configuration hash and code commit.
- Verify the UTC candle-open contract, feature cutoff, target window and no-future-input rule.
- Reproduce baseline and declared cost-sensitivity calculations.
- Verify that stale, missing, invalid and unresolved rows are quarantined rather than silently scored.
- Retain the KILLED verdict and zero-survivor result without retuning on the same OOS interval.
- Record data-source outages, provider failover and external-context gaps.

## Go / no-go

**GO:** a bounded methodology review using the frozen historical evidence and local synthetic UI, if the customer accepts the limits.

**NO-GO:** a live-data predictive-performance pilot or any profitability claim today.

No real broker trade or order has been executed.
