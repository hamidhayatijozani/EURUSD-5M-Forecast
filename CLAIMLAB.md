# CLAIMLAB

ClaimLab is the falsification layer for EURUSD-5M-Forecast.

It does not ask whether the engine looks intelligent. It asks whether a measurable claim survives reality.

## Claim lifecycle

CLAIM → PRE-REGISTER → LOCK → FORECAST → RESOLVE → COST → BASELINE → STATISTICAL TEST → SURVIVE / KILL

## Non-negotiable rules

1. Forecast timestamps are immutable.
2. No future candle, news, trader signal or derived feature may enter a forecast.
3. Every claim has a baseline.
4. Costs/friction are applied before declaring an edge.
5. OOS observations are not used to tune the same claim.
6. Failed hypotheses are retained and marked KILLED, not silently removed.
7. A code/test pass is not a market-success claim.

## Core claims

- C001: combined engine improves MAE versus baseline.
- C002: combined engine improves friction-adjusted directional return versus baseline.
- C003: adaptive algorithm weighting improves over static combination.
- C004: external context adds incremental information after controlling for the internal engine.
- C005: top-50 trader context adds incremental information.
- C006: candle-pattern/deep-structure features add incremental information.

Each claim must report n, MAE, hit rate, average friction-adjusted return, baseline delta, confidence interval where applicable, and the exact evaluation window.

## Kill rule

A claim is KILLED when its preregistered OOS criterion fails. We do not rescue it by changing thresholds after seeing the result.

This is deliberately harsher than marketing. Markets have enough fiction already.
