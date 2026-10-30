# EURUSD-5M Forecast — Customer Evaluation Brief
**Evidence cut-off:** 2026-10-30 06:03:47 UTC  
**Product posture:** research/evaluation software, not a proven trading strategy  
**Decision:** **NO-GO for a live-data or predictive-performance pilot today; GO for a scoped methodology review using frozen historical evidence and the local synthetic UI.**

## Executive summary

The repository now has a reproducible historical ClaimLab pipeline, explicit UTC candle contracts, duplicate/invalid-row rejection, separate spread/slippage scenarios, forecast-time evidence snapshots, and a paper-only live evaluation loop.

The tested historical rolling-mean claim is **KILLED**. The preregistered candidate arena has **zero survivors**. The latest live-minute cycle obtained one fresh Yahoo EURUSD snapshot and emitted one FLAT forecast, but four later cycles were held because the feed aged beyond its 90-second freshness limit. OANDA was not configured; Twelve Data returned no closed candles in that run. The paper account is negative after assumed costs.

This software can demonstrate an auditable research process. It cannot currently support a claim of predictive superiority or profitability.

## Verified historical ClaimLab evidence

Source: [ClaimLab historical walk-forward run 41011392998](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392998); [evidence artifact](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392998/artifacts/12958091586).

| Item | Observed result |
|---|---|
| Claim registry | `EURUSD-5M-CORE-001`, status `LOCKED` |
| Historical dataset | 37,948 rows, 2026-03-26 02:30 UTC through 2026-09-25 20:55 UTC |
| Dataset SHA-256 | `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6` |
| Effective sample | 37,584 observations |
| Temporal rejects | 0; temporal validity 100% |
| Baseline | Zero-return |
| Candidate | 12-bar rolling-mean-return |
| Baseline MAE | `0.0001254450` |
| Candidate MAE | `0.0001320492`, worse than baseline |
| MAE difference vs baseline | `-0.0000066042`; 95% block-bootstrap CI `[-0.0000070606, -0.0000061539]` |
| Directional hit rate | 41.56% |
| Mean return after assumed 0.2-pip spread | `-0.0000221582`; 95% CI `[-0.0000239873, -0.0000203259]` |
| Claim verdict | **KILLED** |

### Separate spread and slippage sensitivity

These are declared round-trip scenarios, not executable broker quotes. Commission is not priced because no broker/venue commission schedule was supplied.

| Spread | Slippage | Mean friction-adjusted return |
|---:|---:|---:|
| 0.2 pip | 0.00 pip | -0.0000221582 |
| 0.2 pip | 0.10 pip | -0.0000321582 |
| 0.5 pip | 0.10 pip | -0.0000621582 |
| 1.0 pip | 0.25 pip | -0.0001271582 |

The confidence interval for the primary scenario is wholly negative. No performance claim is permitted from this candidate.

## Preregistered candidate arena and post-cutoff OOS

Source: [ClaimLab candidate arena run 40856430115](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40856430115); [evidence artifact](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40856430115/artifacts/12889326893).

- Nine frozen candidates were evaluated across chronological train/validation/test partitions.
- A separate post-cutoff OOS interval contained 6,529 observations.
- `parameter_tuning_on_oos=false`.
- Survivors: **none**. Verdict: **KILLED**.
- The OOS interval must not be reused for tuning and then presented as independent evidence.

## Live-feed and forward-paper evidence

Source: [live-minute-research run 41011372782](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011372782).

- Provider failover: `oanda:NOT_CONFIGURED`, `twelvedata:NO_CLOSED_CANDLES`, then Yahoo selected.
- One EURUSD 1-minute forecast was emitted from a closed candle at 05:57 UTC and issued at 05:58 UTC.
- Data age at observation: **78.35 seconds**, below the 90-second limit; freshness status `FRESH`.
- Forecast direction: `FLAT`; prediction: 0; status at issuance: `PENDING`.
- Four later cycles were held as evidence age reached 95.8s, 99.6s and 103.3s. No stale forecast was emitted.
- Cross-asset market research fell back to Yahoo EURUSD-only because only 23 common closed candles were available while 63 were required — [run 41011392830](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392830).
- External context coverage was 0: GDELT returned a URL error, Electricity Maps had no API key, and no trader signal file was present.

### Paper-account result

The same live-minute run evaluated a paper-only account. No broker orders were placed.

| Item | Result |
|---|---:|
| Input rows | 398 |
| Eligible resolved predictions | 276 |
| Missing/invalid-evidence rows | 34 |
| Unresolved rows | 48 |
| Wrong/missing-contract rows | 40 |
| Paper trades | 208 |
| Wins / losses | 69 / 139 |
| Win rate | 33.17% |
| Net PnL at assumed 0.2-pip cost | -8.34 on 10,000 starting balance |
| Net PnL at assumed 0.5-pip cost | -20.80 |
| Net PnL at assumed 1.0-pip cost | -41.54 |

The live cross-asset v2 family had 279 resolved observations. Every candidate remained `INSUFFICIENT_DATA`; no candidate survived the statistical gate. The paper evaluator explicitly recorded `profitability_claim_allowed=false` and `edge_claim_allowed=false`.

The post-timezone-fix live run [41011392858](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/41011392858) was still in progress at this evidence cut-off. No Twelve Data recovery is claimed here.

## Demo status

- **Local UI:** `dashboard/index.html`. Its interactive example values are synthetic; suitable for demonstrating interface and workflow only, not live performance.
- **Hosted demo:** **BLOCKED**. [Deploy run 40633481081](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40633481081) failed because the Pages site was not found and the integration could not create it. No public hosted demo is claimed.
- **Methodology:** [CLAIMLAB.md](../../CLAIMLAB.md), [METHODOLOGY.md](../METHODOLOGY.md), and [OPERATIONAL_STATUS.md](../../docs/OPERATIONAL_STATUS.md).

## Proposed limited evaluation pilot

**Proposed fee: US$2,500 for 30 days.** This is a pricing proposal, not an existing contract, customer, payment or revenue record.

### Included
- One customer team, one instrument (EUR/USD), one agreed forecast horizon.
- Read-only research and evidence review; no broker credentials, account access or order placement.
- Frozen historical report, data/provenance checks, baseline comparison, declared spread/slippage sensitivity, and weekly evidence summary.
- Final report retaining failed hypotheses and reporting `SURVIVE`, `KILLED` or `INSUFFICIENT_DATA` under locked criteria.

### Explicit exclusions
- No guaranteed returns, investment advice or claim of a profitable edge.
- No live trading, broker orders, customer-fund access or unrestricted execution.
- No promise of OANDA/Twelve Data availability or external context sources that are not actually available.
- No customer-data ingestion until lawful source, retention and access controls are agreed.

### Start gates
1. A fresh live-provider run on the exact pilot commit, with provider, closed-candle timestamp, observation time, age and payload hash recorded across repeated cycles.
2. OANDA or Twelve Data configured and independently observed if the customer requires those providers; Yahoo fallback alone must be explicitly accepted.
3. At least 1,000 resolved observations for the frozen forward-paper claim family and the preregistered minimum trade count; no candidate may be promoted from an insufficient sample.
4. Customer-approved executable spread, slippage and commission inputs; declared scenario values are not broker-cost evidence.
5. Customer can reproduce the frozen historical report from dataset hash, locked registry, configuration hash and code commit.
6. Customer accepts the local synthetic demo or a repository owner successfully enables a hosted demo.
7. Data rights, retention, evaluation window and support boundaries agreed in writing.

### Acceptance criteria

Acceptance concerns reproducibility and system behavior, not profit:
- Zero detected future-input or temporal-contract violations in the agreed test set.
- Every forecast has source timestamp, observation timestamp, feature cutoff, target window, code commit, configuration hash and decision-evidence hash; invalid rows are quarantined.
- Baseline and cost calculations are reproducible from the frozen evidence bundle.
- Feed freshness, provider failover, exclusions and failure periods are measured and reported.
- No positive-edge claim unless a separately preregistered, untouched OOS test survives after realistic customer-approved costs and multiple-testing correction.

## Go / no-go

**Current decision: NO-GO for a live-data predictive pilot.** A methodology review using the frozen historical artifact and local synthetic UI is possible if the customer explicitly accepts those boundaries.

This is a dated evidence snapshot. Re-run the data, live-feed, walk-forward and paper-settlement gates on the proposed pilot commit before making any current performance statement.
