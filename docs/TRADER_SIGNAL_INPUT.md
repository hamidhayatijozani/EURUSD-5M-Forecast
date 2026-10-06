# Trader signal input contract

The engine does not invent a list of 50 successful traders.

Populate research/trader_signals.jsonl from an authorized public or partner source. Each line is one immutable forecast made before its target window:

{"trader_id":"source/user","prediction_ts":"2026-10-06T12:00:00+00:00","target_ts":"2026-10-06T12:05:00+00:00","entry_price":1.1700,"predicted_return":0.0003,"direction":"UP"}

The live engine evaluates only forecasts whose target has already closed, keeps the last 24 hours, calculates mean absolute error per trader, and selects the 50 lowest-error profiles.

No trader with no observed 24h forecast is silently promoted into the leaderboard.
No future target is used to rank a trader before that target closes.

Possible production adapters include eToro's authorized public API, Myfxbook community data, or another licensed signal provider. Credentials are never committed to git.
