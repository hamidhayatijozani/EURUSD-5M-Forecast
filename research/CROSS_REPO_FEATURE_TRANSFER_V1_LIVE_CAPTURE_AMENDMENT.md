# Amendment 1 — Forward capture of cross-repository feature snapshots

Date: 2026-10-12
Status: **PREREGISTERED BEFORE LIVE-CAPTURE CODE CHANGE; PERFORMANCE NOT EVALUATED**

This amendment supplements CROSS_REPO_FEATURE_TRANSFER_V1. It does not alter the locked ClaimLab core registry, the existing candidate arena registration, or any historical result.

## Purpose

Record the five experimental features alongside existing live-minute forecasts so they can later be evaluated against the exact resolved target. This is evidence capture only, not a signal integration.

## Capture contract

- Input: the existing aligned, closed EUR/USD 1-minute close series already admitted by the live data contract.
- Information cutoff: the issue time of the forecast; only closed bars at or before this cutoff may be used.
- Window: the last 13 closed prices (12 one-minute returns).
- Output: feature version, source timeframe, feature cutoff timestamp, and either finite feature values or an explicit unavailable status/reason.
- Failure isolation: degenerate or invalid experimental features must not suppress, alter, or delay the existing forecast; they are recorded as unavailable.
- Decision isolation: none of the new values may affect direction, score, confidence, ensemble weights, candidate positions, or online calibration in this version.
- Resolution: future evaluation must join snapshots to the existing immutable prediction ID and exact target timestamp, preserving source/dataset hashes and the forward-only boundary.

## Evaluation boundary

The live feature snapshot is a diagnostic observation, not a forecast and not evidence of predictive value. No historical test set may be described as untouched if it has already informed feature/model choices. Performance claims require a separately specified forward evaluation with sufficient valid observations, effective sample size, realistic cost sensitivity, dependence-aware uncertainty, and multiplicity correction. If capture coverage is inadequate, report INSUFFICIENT_DATA.

## Kill / rollback

Drop this capture field if it changes forecast behavior, introduces material latency, creates a timestamp mismatch, or cannot be joined reproducibly to resolved outcomes. The feature values remain experimental until a separate registered test supports an incremental benefit.
