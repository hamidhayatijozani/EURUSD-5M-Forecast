# Issue #36 — Live Evidence Acceptance Audit

Audit captured at: 2026-10-12 05:31 UTC
Repository: `hamidhayatijozani/EURUSD-5M-Forecast`
Integration commit: `c4972a1bc1b8cb22e235753058d5c269da77ee1e`
PR: [#38](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/38)
Live workflow: [run #131](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38208050763)
CI: [research-tests on integration commit](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38208050790), 107 passed.

## Verified at capture time

- Production live loop is connected to immutable decision snapshots, JSONL evidence ledger, SQLite, and settlement audit.
- Live workflow completed successfully: 5 cycles, 4 forecasts, 0 holds, 0 errors.
- End-of-cycle audit output: `status=AUDITED, predictions=4, snapshots=4, settlements=0`.
- Four real-feed forecast records exist in `research/live_predictions.jsonl` and four matching evidence records exist in `research/live_decision_evidence.jsonl`.
- Snapshot references in the live prediction rows match the evidence ledger's snapshot hashes.
- Model, feature, signal, and research freezes remain in effect. No predictive-edge claim is made.

## Pending acceptance

No target had been settled at capture time. The first eligible target is `2026-10-12T05:32:00+00:00` for prediction `live-eurusd-1m-20261012T052600Z`.

Issue #36 remains **PENDING** until a later live run records the actual target price, appends the unique settlement to SQLite and the settlement JSONL, and emits a passing audit with at least one settled prediction. A successful CI run or issuance-only audit is not sufficient.

## Current external context limitation

The recorded live cycle reports news unavailable (`URLError`), electricity context unavailable (`NO_API_KEY`), and trader leaderboard unavailable (`NO_SIGNAL_FILE`). These sources are not represented as available evidence.


## Final acceptance update — 2026-10-12 05:34 UTC

**Issue #36 minimum acceptance: PASS for the first fully auditable live prediction.**

- Merged integration commit: `c4972a1bc1b8cb22e235753058d5c269da77ee1e`.
- Post-merge live workflow: [run #132](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38208321896), conclusion `success`.
- Full CI: 107 tests passed on the integration PR; the post-merge live workflow's test step also passed.
- Live cycle summary: `cycles=5 forecasts=4 holds=0 no_new_forecast=1 errors=0`.
- Final dual-store audit output: `status=AUDITED, predictions=8, snapshots=8, settlements=3`.
- The audit verifies JSONL hash-chain integrity, snapshot/hash references, matching prediction identities in JSONL and SQLite, and parity of settlement IDs between SQLite and the settlement JSONL.
- Three post-merge real-feed predictions reached their targets and were settled exactly once:
  - `live-eurusd-1m-20261012T052600Z`: target `05:32:00Z`, actual return `0`.
  - `live-eurusd-1m-20261012T052700Z`: target `05:33:00Z`, actual return `-0.00011203318310104571`.
  - `live-eurusd-1m-20261012T052800Z`: target `05:34:00Z`, actual return `0`.
- The same three IDs are present in the production prediction ledger, ClaimLab settlement observations, and dual-store settlement ledger. Their decision snapshots remain immutable and are linked by their recorded SHA-256 references.

## Interpretation and remaining limits

The evidence-path acceptance gate is now **PASS** for at least one real live prediction; three have been settled and audited. This does **not** establish predictive edge or profitability. The three outcomes above did not produce a correct directional hit, and the sample is far too small to infer skill.

External context remains degraded in the captured run: news unavailable (`URLError`), electricity data unavailable (`NO_API_KEY`), and trader leaderboard unavailable (`NO_SIGNAL_FILE`). These inputs were not represented as available evidence.

Freeze status remains unchanged:
`FEATURE_FREEZE=ACTIVE`, `MODEL_FREEZE=ACTIVE`, `SIGNAL_FREEZE=ACTIVE`, `RESEARCH_FREEZE=ACTIVE`.


## Reopened acceptance follow-up — 2026-10-13 06:26 UTC

This follow-up supersedes the older "final acceptance" status above for the **newly reopened** gate. The earlier three settlements remain valid historical evidence, but do not satisfy the current requirement to settle a new prediction produced after the latest ingestion repair.

### Change and post-merge runtime

- PR [#46](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/pull/46) merged as `d13672a381f796a759fe7daddbfa71f3e0cd100a`.
- Exact PR-head CI [run #38356308289](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38356308289): **123 tests passed**.
- Post-merge live workflow [run #38356397344, attempt 1](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/38356397344): conclusion `success`.
- Runtime artifact: `live-minute-diagnostics-142`, artifact ID `11793265232`, generated 2026-10-13 06:26:12 UTC.
- Cycle summary: `cycles=5 forecasts=3 holds=1 no_new_forecast=1 errors=0`.
- Final runtime audit line: `status=AUDITED, predictions=41, snapshots=41, settlements=34`.

The new provider validator is exercised in real logs: Twelve Data attempts are rejected with `ValueError` or an HTTP error and the feed selector falls through to Yahoo. This demonstrates functioning failover; it does **not** establish Twelve Data as a valid source in this run.

### Independent artifact audit

The downloaded artifact was checked directly against its JSONL files and SQLite database. Results:

- 41 unique prediction IDs in the decision-evidence JSONL and 41 predictions in SQLite; exact ID-set parity.
- All 41 evidence hashes validate; all 41 snapshot-content hashes validate.
- The entire decision-evidence JSONL hash chain validates.
- All 41 snapshot IDs, hashes, and snapshot payloads match between JSONL and SQLite.
- 34 settlement IDs and payloads match between settlement JSONL and SQLite.
- Every settlement is at or after its target time, refers to an issued prediction, and references that prediction's recorded snapshot hash.
- No orphan settlements or duplicate prediction IDs were found in the artifact.

These checks apply to the captured artifact, not to predictions created after the artifact was uploaded.

### Newly issued predictions still pending at capture

At artifact time, the following post-merge predictions had issuance snapshots but had not yet reached their target timestamps:

| Prediction ID | Issued at | Target at | Provider | Capture status |
|---|---|---|---|---|
| `live-eurusd-1m-20261013T062200Z` | `2026-10-13T06:23:00Z` | `2026-10-13T06:28:00Z` | `yahoo` | `PENDING` |
| `live-eurusd-1m-20261013T062300Z` | `2026-10-13T06:24:00Z` | `2026-10-13T06:29:00Z` | `yahoo` | `PENDING` |
| `live-eurusd-1m-20261013T062400Z` | `2026-10-13T06:25:00Z` | `2026-10-13T06:30:00Z` | `yahoo` | `PENDING` |

Therefore the re-opened Issue #36 acceptance gate remains **PENDING** until a subsequent run settles at least one of these exact new prediction IDs from observed post-target market data and independently audits the updated JSONL/SQLite state. Do not infer settlement just because the target time has passed.

### Predictive-edge and external-context limits

Both forward cross-asset evaluators returned `INSUFFICIENT_DATA` with no surviving candidates. Their preregistered minimums are 1,000 resolved observations and at least 200 trades per candidate; the captured samples are far smaller. No predictive edge or profitability is established.

Context remained degraded: news source unavailable (`URLError`), electricity context unavailable (`NO_API_KEY`), and trader leaderboard unavailable (`NO_SIGNAL_FILE`). These were recorded as unavailable, not treated as successful inputs.

Freeze state remains unchanged:
`FEATURE_FREEZE=ACTIVE`, `MODEL_FREEZE=ACTIVE`, `SIGNAL_FREEZE=ACTIVE`, `RESEARCH_FREEZE=ACTIVE`.
