# Operational Status — EURUSD-5M-Forecast

Last update: **2026-10-30** (UTC)

## Current truth

- Main HEAD at this evidence cut-off: `af656417a7896caca5c037d3ae3602d486639d81` (automated live-evidence persistence commit). The research-tests and historical walk-forward evidence were executed against code SHA `60c432775d9dd6f4d7e5cc219a4871cd7cc234a0`.
- Research test suite: **PASS**, 174 tests — [run 41011392888](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392888).
- Historical ClaimLab walk-forward: **PASS as a reproducible computation; model verdict KILLED** — [run 41011392998](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392998), [evidence artifact](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392998/artifacts/12958091586).
- Multi-source market research: **PASS as a completed job, but falls back to Yahoo EURUSD-only** because only 23 common closed candles were available and 63 were required — [run 41011392830](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392830).
- Live-feed verification: **PARTIAL**. [Live-minute run 41011372782](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011372782) selected Yahoo after `oanda:NOT_CONFIGURED` and `twelvedata:NO_CLOSED_CANDLES`. It emitted one fresh EURUSD 1-minute forecast (data age 78.35s against a 90s limit), then held four cycles as evidence aged past the limit (95.8s, 99.6s, 103.3s). This proves one fresh Yahoo snapshot, not a sustained feed or Twelve Data/OANDA availability. The post-timezone-fix live run [41011392858](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392858) is still in progress.
- Live broker execution and real-money orders: **NOT_RUN**. The workflows evaluate data and paper ledgers only.

## Historical ClaimLab walk-forward

- Source: real historical EUR/USD 5-minute OHLCV CSV, not synthetic demo data.
- Dataset SHA-256: `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6`.
- Rows: 37,948; valid sequential observations: 37,584.
- Temporal validity rate: 1.0; duplicate prediction rate: 0.0; ledger integrity: 1.0.
- Baseline: zero predicted return.
- Candidate: 12-bar rolling-mean-return predictor.
- Verdict: **KILLED**.

| Metric | Result | Interpretation |
|---|---:|---|
| Baseline MAE | 0.0001254450 | Zero-return reference |
| Candidate MAE | 0.0001320492 | Worse than baseline |
| MAE improvement vs baseline | -0.0000066042 | Negative |
| 95% block-bootstrap CI for MAE improvement | [-0.0000070606, -0.0000061539] | Entire interval below zero |
| Directional hit rate | 0.415629 | Below 0.50 |
| Net mean return at 0.2-pip spread-only assumption | -0.0000221582 | Negative |
| 95% block-bootstrap CI for net mean return | [-0.0000239873, -0.0000203259] | Entire interval below zero |

### Separate spread and slippage sensitivity

These are declared scenarios, not observed broker quotes. Commission is **not priced** because no broker/venue commission schedule was supplied.

| Round-trip spread | Round-trip slippage | Net mean return |
|---:|---:|---:|
| 0.2 pip | 0.00 pip | -0.0000221582 |
| 0.2 pip | 0.10 pip | -0.0000321582 |
| 0.5 pip | 0.10 pip | -0.0000621582 |
| 1.0 pip | 0.25 pip | -0.0001271582 |

The confidence interval for the primary 0.2-pip scenario is wholly negative. No profitability or predictive-edge claim is allowed.

## Preregistered candidate arena and post-cutoff OOS

- Workflow: [ClaimLab preregistered candidate arena, run 40856430115](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40856430115).
- Evidence artifact: [candidate-arena-evidence](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40856430115/artifacts/12889326893).
- Nine frozen candidates, including momentum, contrarian, breakout, wick-reversal and no-trade control.
- Chronological split: 22,348 train observations, 7,450 validation observations, 7,450 test observations.
- Separate post-cutoff OOS: 6,529 observations, beginning after the locked historical cutoff; `parameter_tuning_on_oos=false`.
- Survivors: **none**. Verdict: **KILLED**.
- Broker costs were not verified; the arena's 0.2/0.5/1.0-pip sensitivity values are assumptions, not executable venue quotes.

The killed candidate and empty survivor set must remain visible. Do not retune on the OOS interval and then reuse that interval as independent evidence.

## Data and timestamp contract

- Historical candle timestamps identify candle open.
- Timezone-aware values normalize to UTC; the canonical historical CSV's naive timestamps are interpreted as UTC by declared source contract.
- Duplicate candle timestamps, non-finite values, non-positive prices, inconsistent OHLC, negative volume and empty datasets are rejected.
- Walk-forward forecasts are issued after the feature bar closes and resolve at the next contiguous 5-minute bar close. Gaps are skipped rather than treated as five-minute targets.
- PR #76 added deterministic UTC normalization, row validation, duplicate rejection, and separate spread/slippage scenarios; merged as `d4c9c99fdd14080cde572a7bfb837533f8cc3a31`.
- PR #77 pinned Twelve Data intraday requests to `timezone=UTC` and explicitly requested OHLC fields; merged as `60c432775d9dd6f4d7e5cc219a4871cd7cc234a0`. The 174-test main run passed, but the live workflow has not yet supplied a fresh Twelve Data/OANDA observation proving that the provider fix restored live coverage.

## Forward-paper evidence and provider limitations

- The live-minute run above recorded one `FLAT` forecast with `signal_contradiction=true`, `context_coverage=0`, `news_status=UNAVAILABLE:URLError`, and `power_status=UNAVAILABLE:NO_API_KEY`. It did not place an order.
- Its paper-account evaluation used 398 input rows: 276 eligible resolved predictions, 34 missing/invalid-evidence rows, 48 unresolved rows, and 40 wrong/missing-contract rows. The 208 paper trades had 69 wins and 139 losses (33.17% win rate). Net PnL was -8.34 on a 10,000 starting balance at the assumed 0.2-pip cost, -20.80 at 0.5 pip, and -41.54 at 1.0 pip. `profitability_claim_allowed=false`.
- The frozen live cross-asset v2 family had 279 resolved observations; all candidates remained `INSUFFICIENT_DATA`, no candidate survived, and the reported two-sided bootstrap p-values were 1.0. This is not evidence of an edge.
- The multi-source research run [41011392830](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392830) completed but fell back to Yahoo EURUSD-only because only 23 common closed candles were available (63 required).
- A separate historical-data probe [41011372878](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011372878) found the historical dataset 2,970,224 seconds old against a 900-second freshness threshold; that result is about the historical artifact, not the one fresh Yahoo minute snapshot above.

## Required before a customer can treat this as live-data research

1. Complete a successful live-provider probe and preserve a fresh closed candle with provider, UTC timestamp, age and payload hash.
2. Resolve the common-candle coverage gap across the required symbols; do not silently describe the EURUSD-only fallback as multi-source confirmation.
3. Obtain executable bid/ask spread, slippage and commission observations from the intended broker/venue. Declared scenarios are not broker-cost evidence.
4. Freeze a new hypothesis, feature set, thresholds, cost assumptions and multiplicity plan before any further OOS evaluation. Do not tune against the killed candidate's OOS interval.
5. Require a surviving candidate under the locked statistical gate, then run a fresh forward-paper evaluation with ledger-backed settlements before making any economic claim.

## Explicit non-claims

- No guaranteed edge or profitability.
- No live-feed availability inferred from historical artifacts or a successful synthetic adapter test.
- No broker-cost verification.
- No OANDA verification unless a separate read-only OANDA probe is evidenced.
- No broker order execution or real-money trading.
