# EURUSD-5M Forecast — Customer Evaluation Brief
**Evidence cut-off:** 2026-10-28  
**Product posture:** research/evaluation software, not a proven trading strategy  
**Decision:** **NO-GO for a live-data customer pilot today; GO for a scoped methodology review using the frozen historical evidence and local demo source.**

## Executive summary

EURUSD-5M-Forecast records forecast-time inputs, freezes the temporal information set, resolves forecasts after the target window, and evaluates pre-registered claims against a baseline after declared friction. ClaimLab is designed to falsify weak claims, not to manufacture a marketing win.

The latest checked historical walk-forward run **killed** the tested claim. The software can demonstrate an auditable research process, but the current evidence does **not** support a claim of predictive superiority or profitability.

## Verified research evidence

Source: GitHub Actions run [ClaimLab historical walk-forward evidence](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40633481066), completed 2026-10-28. The run produced a `claimlab.evidence_capsule.v1` artifact.

| Item | Observed result |
|---|---|
| Claim registry | `EURUSD-5M-CORE-001`, status `LOCKED` |
| Historical dataset | 37,948 rows, 2026-03-26 02:30 UTC through 2026-09-25 20:55 UTC |
| Dataset SHA-256 | `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6` |
| Effective sample size | 37,584 |
| Temporal rejects | 0 in this run; reported temporal validity 100% |
| Baseline | Zero-return |
| Declared base friction | 0.2 pip round trip (`0.00002` in EUR/USD price units); this is a scenario, not a broker quote |
| Mean friction-adjusted return | `-0.0000221582`, approximately **-0.222 pip per observation** |
| 95% confidence interval | `[-0.0000239873, -0.0000203259]`, entirely below zero |
| Reported hit rate | 41.56%; reported p-value 1.0 |
| Baseline MAE | `0.0001254450` |
| Candidate MAE | `0.0001320492`, worse than baseline by about `0.0000066042` |
| Claim verdict | **KILLED** |

The run used historical sequential out-of-sample regimes, a past-only expanding warm-up, a rolling 500-observation volatility lookback, threshold refresh every 25 observations, and 50 warm-up observations excluded. The run's own scientific boundary states that this is historical research evidence, not proof of live predictive superiority or profitability.

### Declared cost sensitivity

These are scenario calculations, **not executable broker costs**.

| Round-trip friction scenario | Mean friction-adjusted return | Approx. pips/observation |
|---|---:|---:|
| 0.2 pip | `-0.0000221582` | -0.222 |
| 0.5 pip | `-0.0000521582` | -0.522 |
| 1.0 pip | `-0.0001021582` | -1.022 |

No performance claim should be made from this candidate. A new hypothesis requires its own pre-registration and untouched out-of-sample evaluation.

## Data provenance and current live-pipeline boundary

The canonical-ledger integration audit passed in [workflow run 40636545043](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40636545043): 389 source rows, 349 provenance/freshness-eligible rows, 40 excluded rows, row counts reconciled, and the source SHA-256 remained unchanged (`6435439cb2f6fd1108582d3d9f8de889bf0e979bc3585d58129d6a9582903297`). “Eligible” means the audit's metadata criteria were met; it does not independently prove the market data is true or that a forecast has edge.

The latest checked live-minute workflow [failed](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40633481098). Its log contains `ValueError: INVALID temporal ordering` and later `ALL_MARKET_PROVIDERS_FAILED`. The latest persisted prediction snapshot checked in the repository had source candle time `2026-10-28T04:47:00Z`; continued live freshness is therefore **not established**. PR [#71](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/71) proposes single-snapshot reuse and quarantine of invalid pending rows; its CI must pass and the resulting live pipeline must produce fresh evidence before a live-data pilot starts.

## Demo status

- **Local source demo:** `dashboard/index.html` in the repository. The README explicitly says its interactive values are synthetic. It is suitable for showing the interface and workflow only, not for demonstrating live forecast performance.
- **Hosted demo:** **BLOCKED.** [Deploy run 40633481081](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40633481081) failed at Configure Pages because the Pages site was not found and the integration could not create it (`Resource not accessible by integration`). No public hosted demo is claimed.
- **Methodology:** [CLAIMLAB.md](../CLAIMLAB.md), [research/METHODOLOGY.md](../METHODOLOGY.md), and [CONSENSUS_CLAIMLAB_PROTOCOL.md](CONSENSUS_CLAIMLAB_PROTOCOL.md).

## Proposed limited evaluation pilot

**Proposed fee:** **US$2,500 for 30 days**, fixed scope. This is a proposal, not an existing contract, customer, payment, or revenue record.

### Included
- One customer team, one instrument (EUR/USD), one agreed forecast horizon.
- Read-only research workflow and evidence review; no broker credentials or order placement.
- A frozen evaluation protocol, data/provenance checks, cost-sensitivity report, baseline comparison, and weekly evidence summary.
- A final report that retains failed hypotheses and reports `SURVIVE` or `KILLED` under the locked criteria.

### Explicit exclusions
- No guaranteed returns, investment advice, or claim of a profitable edge.
- No live trading, broker orders, customer-fund access, or unrestricted execution.
- No promise of private trader-position data or external context sources that are not actually available.
- No customer data ingestion until lawful source, retention, and access controls are agreed.

### Start gates
1. A fresh live-data cycle succeeds on the exact pilot commit, with timestamps and provenance recorded.
2. The single-snapshot/quarantine fix in PR #71 passes CI and does not admit invalid temporal rows into ClaimLab.
3. The customer can reproduce the frozen historical report from the dataset hash, locked registry, configuration hash, and code commit.
4. The hosted demo is enabled by a repository owner, or the customer explicitly accepts a local/source-only demonstration.
5. Customer and provider agree in writing on data rights, retention, evaluation window, and the spread/slippage/commission scenarios.

### Acceptance criteria

Acceptance is about reproducibility and system behavior, not profit:
- Zero detected future-input/temporal-contract violations in the agreed test set.
- Every emitted pilot forecast has a traceable source timestamp, observation timestamp, feature cutoff, target window, code commit, configuration hash, and decision-evidence hash; invalid rows are quarantined.
- Cost and baseline calculations are reproducible from the frozen evidence bundle.
- Feed availability, freshness, exclusions, and failure periods are measured and reported; any agreed uptime target is evaluated against the actual feed, not assumed.
- A signed final report lists all unresolved failures and makes no positive-edge claim unless a separately preregistered OOS test survives after realistic, customer-approved costs and multiple-testing correction.

## Go / no-go

**Current decision: NO-GO for a live-data pilot.** The historical audit is reproducible and the candidate was honestly killed, but the latest live pipeline failed and the hosted demo is not deployed. A research-methodology review using the frozen artifact and local synthetic UI is possible if the customer understands those limits.

This document is a dated evidence snapshot. Re-run the audit and walk-forward workflow on the proposed pilot commit before using it as a current performance statement.
