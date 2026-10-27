# Operational Status — EURUSD-5M-Forecast

Last update: **2026-10-27** (UTC)

## Current truth

- **Historical ClaimLab candidate:** `KILLED` under the locked performance criteria.
- **Historical evidence reproducibility:** PASS. The latest evidence artifact contains the exact source CSV, observation ledger, and capsule. The source file SHA-256 matches the capsule's `dataset_sha256`.
- **Temporal validity:** 1.0.
- **Duplicate prediction rate:** 0.0.
- **Ledger integrity:** 1.0.
- **Live provider probe:** NOT RUN in the latest validation cycle. The optional live-probe job was skipped; do not infer current feed availability from synthetic tests or the historical run.
- **Live trading / broker orders:** not run by this pipeline.
- **Profitability:** not established.

## Latest historical walk-forward evidence

- Workflow: [ClaimLab historical walk-forward evidence, run 40542254822](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40542254822)
- Evidence artifact: [claimlab-walkforward-evidence-40542254822](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40542254822/artifacts/12751695537)
- Artifact contains: `dataset.csv`, `observations.jsonl`, `evidence_capsule.json`.
- Historical source: [EUR/USD 5-minute OHLCV CSV](https://raw.githubusercontent.com/getdata-finance/eurusd-5m-ohlcv-forex-historical-data/main/EURUSD_5m.csv)
- Dataset SHA-256: `8c6caff3b52b7bf74c7836297e51d405cd1ecb30f0e02cc5bf2fb85ae0afd3f6`
- Rows: 37,948; valid one-step walk-forward observations: 37,584.
- Effective sample size: 37,584.
- Baseline: zero predicted return.
- Candidate: 12-bar rolling-mean-return predictor.
- Verdict: **KILLED**.

| Metric | Result | Interpretation |
|---|---:|---|
| MAE improvement vs zero-return baseline | -0.0000066042 | Candidate is worse |
| 95% block-bootstrap CI for MAE improvement | [-0.0000070606, -0.0000061539] | Entire interval below zero |
| Directional hit rate | 0.415629 | Below 0.50 |
| Mean friction-adjusted return | -0.0000221582 | Negative under declared cost |
| 95% block-bootstrap CI for friction-adjusted return | [-0.0000239873, -0.0000203259] | Entire interval below zero |

The evidence capsule reports `predictive_edge_established=false`, `profitability_established=false`, and `live_feed_verified=false`. The source snapshot hash was independently checked against the capsule hash after artifact download.

The cost model is a sensitivity assumption: 0.2 pip base round-trip friction, with slippage and commission set to zero in the primary run. The separate cost-sensitivity report evaluates 0.2, 0.5, and 1.0 pip scenarios, but these are not observed broker quotes. No result should be presented as an executable trading strategy or profit claim.

## Twelve Data ingestion

- Workflow: [Twelve Data EURUSD ingestion, run 40541563712](https://github.com/hamidhayatijozani/EURUSD-5M-Forecast/actions/runs/40541563712)
- Synthetic adapter tests and the full test suite passed.
- The optional live-provider probe was skipped in that run. A live observation requires a manual workflow dispatch with `run_live_probe=true` and the repository secret `TWELVEDATA_API_KEY`.
- The adapter now reads `TWELVEDATA_API_KEY` first and preserves `TWELVE_DATA_API_KEY` as a legacy alias. The secret name is never printed by the probe.

## Required before a customer can treat this as live-data research

1. Run the optional live-provider probe with the documented secret configured.
2. Verify a fresh closed candle and inspect the sanitized evidence record, including provider, timestamp, age, and payload hash.
3. Keep the historical ClaimLab verdict separate from any new model or live-feed claim.
4. Before evaluating another model family, preregister its claim, features, thresholds, cost assumptions, and multiplicity plan; do not tune on the killed candidate's final evaluation period.
5. Use executable bid/ask and slippage observations before making an economic or trading-cost claim.

## Explicit non-claims

- No guaranteed edge or profitability.
- No broker execution or real-money orders.
- No current live-feed availability inferred from historical artifacts.
- No OANDA verification unless a read-only OANDA probe is separately run and evidenced.
