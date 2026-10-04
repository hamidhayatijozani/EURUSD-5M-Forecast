# Methodology

The baseline uses only information available before the target window.

Signals:
- short momentum
- multi-candle momentum
- rolling direction/range context
- cross-horizon agreement

Output:
- UP, DOWN, or FLAT
- confidence
- regime
- signed score

Evaluation should report directional accuracy, signed and absolute return error, Brier score, calibration, and regime-conditioned accuracy.

Consensus signals are stored separately from ground truth. A consensus is a collection of opinions, not evidence that the future happened as predicted.

The temporal lock is a first-class product invariant: a forecast is valid only when created_at <= target_start < target_end.
