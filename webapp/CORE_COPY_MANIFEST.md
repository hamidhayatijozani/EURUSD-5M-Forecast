# Web application copy manifest

Canonical source: https://github.com/hamidhayatijozani/EURUSD-5M-Forecast

## Preserve, do not reimplement

| Capability | Canonical source | Web application treatment |
|---|---|---|
| Forecast logic and temporal validity | Python engine and temporal lock in source repository | Keep engine authoritative; do not duplicate algorithm in browser |
| Minute issuance and target resolution | `scripts/live_minute_loop.py` | Display only actual ledger output |
| Prediction records | `research/live_predictions.jsonl` | User-importable JSONL for this initial UI |
| Resolved observations | `research/claimlab_live_observations.jsonl` | Add adapter only after schema verification |
| Claim registry and statistical tests | `claimlab/`, `research/CONSENSUS_CLAIMLAB_PROTOCOL.md` | Surface claims only with raw, traceable results |
| CI and deployment evidence | `.github/workflows/` | Do not infer status from the existence of workflow files |

## Explicitly excluded

- Copying synthetic dashboard numbers into a live-looking screen.
- Adding indicators, features, model families, or data sources during the current freeze.
- Claiming profitability or live broker execution.
- Treating missing fields or absent runs as successful evidence.

## Next integration boundary

A verified backend API should expose immutable forecast records, resolution records, data-source provenance, evidence hashes, commit SHA, and CI run identifiers. The UI should show `UNKNOWN` until each field is returned and validated. No credentials belong in browser code.
