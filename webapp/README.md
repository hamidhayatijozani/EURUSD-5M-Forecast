# ClaimLab Web

A browser-first evidence interface for the canonical `hamidhayatijozani/EURUSD-5M-Forecast` project.

## Purpose

This is a separate web interface layer over the existing forecasting and research assets. It does not replace, fork, or silently rewrite the Python forecast engine. The canonical repository remains the source of truth for model logic, temporal locks, ClaimLab evaluation, and CI evidence.

## Open

Open `index.html` in a modern browser, then import an actual `research/live_predictions.jsonl`, JSON, or CSV file. The browser processes the selected file locally; it does not upload it.

## Truth boundary

- No live price feed is bundled or claimed.
- No forecast is invented when there is no input ledger.
- No predictive edge, profitability, broker execution, or CI success is implied.
- Missing timestamps yield `UNKNOWN`, not a pass.
- The temporal check requires `feature_cutoff_at < issued_at < target_ts`; field aliases are best-effort for inspection, not a replacement for the canonical engine contract.
- This client-side UI cannot verify server-side SQLite readback, cryptographic signatures, source authenticity, CI runs, or deployment state.

## Canonical engine map

- `claimlab/`: claim registry and evaluation logic
- `scripts/live_minute_loop.py`: minute loop and ledger writer
- `research/live_predictions.jsonl`: live prediction ledger
- `research/claimlab_live_observations.jsonl`: resolved observation ledger
- `research/CONSENSUS_CLAIMLAB_PROTOCOL.md`: preregistered research protocol
- `research/PRODUCT_STATUS.md`: product boundary and known limitations

All canonical files remain in the source repository. This UI is an inspectable, non-authoritative presentation layer until a backend adapter is explicitly implemented and verified.
