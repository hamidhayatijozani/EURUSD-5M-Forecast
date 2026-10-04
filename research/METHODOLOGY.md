# Forecast methodology

The first model is intentionally transparent.

Baseline inputs: short momentum, 3-candle momentum, 12-candle momentum, rolling range/volatility, current position in recent range, and agreement between momentum horizons.

Outputs: UP / DOWN / FLAT, confidence in [0,1], regime, and expected path.

Trader consensus is recorded as a separate signal family. It must never become ground truth.

Evaluation: directional accuracy, signed return error, absolute return error, Brier score, confidence calibration, and regime-conditioned accuracy.

A forecast is valid only when its creation time precedes its target window.
