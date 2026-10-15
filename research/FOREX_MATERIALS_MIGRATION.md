# Forex Repository Material Consolidation

Status: **RESEARCH-ONLY MIGRATION — NOT MERGED; NO LIVE DATA OR EDGE CLAIM**

Scope: source-code search across the 14 repositories visible to the linked GitHub account, followed by source-file inspection for EUR/USD, FX providers, trader consensus, forecasting evaluation, cross-asset context, P/S/T features, and broker integration. The target remains `EURUSD-5M-Forecast`; the intent is to preserve useful work without importing mock execution or silently changing the live forecast.

## 1. Transferred into this repository

### Rolling EUR/USD trader ranking
- Source: [EURUSD-5M-ForecastHamid/src/trader-intelligence.js](https://github.com/hamidhayatijozani/EURUSD-5M-ForecastHamid/blob/main/src/trader-intelligence.js)
- Source blob SHA: `a168d4ce1d57ae5e569cf42a21ea6ed0699ab236`
- Related source tests: [trader-intelligence.test.js](https://github.com/hamidhayatijozani/EURUSD-5M-ForecastHamid/blob/main/tests/trader-intelligence.test.js), blob SHA `066779ac7bd5a9cc489800b586a5c17736e46607`
- Destination implementation: `engine/trader_intelligence.py`
- Destination tests: `tests/test_trader_intelligence.py`

The useful idea is a rolling 48-hour ranking, capped at 50 eligible providers, with scores based on profit factor (30%), win rate (25%), sample size (20%), drawdown quality (15%), and supplied consistency (10%). The result is a bounded directional summary derived from the sign of each provider's EUR/USD long-equivalent realized profit.

The Python port intentionally tightens several source assumptions:
- Only explicit `EURUSD` trades with `BUY`/`SELL`, a timezone-aware close timestamp, finite realized P/L, and a timestamp inside the 48-hour window count.
- Future or stale trades, unspecified symbols, invalid directions, malformed numbers, and records without positive net P/L are excluded.
- Missing 48-hour drawdown or consistency metadata receives a zero component and a quality warning; it is not silently treated as zero risk or perfect consistency.
- An unbounded profit factor is represented with JSON-safe fields rather than emitting infinity.
- Ranking ties are deterministic. The output includes score components and data-quality warnings.

This is a **ranking mechanism over caller-supplied records**, not a trader discovery service. Source identity, authorization, timestamps, closed-trade semantics, realized P/L, and metadata must be validated by the upstream collector. No such live trader dataset was supplied or fetched here.

## 2. Forex components reviewed but deliberately not copied

| Source repository and file | What inspection found | Decision |
|---|---|---|
| [hamidcognition-realtime/api/forex_data.py](https://github.com/hamidhayatijozani/hamidcognition-realtime/blob/main/api/forex_data.py), blob `cc6d0e99a6ffe81b8dcd642e59bdbe8aaff878f4` | Yahoo Finance price/history, Alpha Vantage fallback, 30-second cache and RSI/trend/volatility helpers. It hardcodes an Alpha Vantage `demo` key, may return stale cached data without an explicit stale status, and logs raw exception strings. | Do not copy into the canonical feed. The target already has normalized multi-provider candle adapters and failover. Reuse the ideas only if a separately tested feature contract needs them. |
| [HamidCognition/eurusd_engine.py](https://github.com/hamidhayatijozani/HamidCognition/blob/master/eurusd_engine.py), blob `035ac721715f2274c0cfcb3cd727deded01ed7b2` | Defines `MockMT5`, generates random synthetic prices/candles and simulates successful logins/orders. | Excluded from the live data and forecast path. Mock broker activity is not evidence of real market access or execution. |
| [HamidCognitionEngine/forex_trading_bot.py](https://github.com/hamidhayatijozani/HamidCognitionEngine/blob/master/forex_trading_bot.py), blob `31fd342bf5056d7d0c1a1c3b5210177370f236d7` | SMA-cross backtest and simulated position accounting. Execution assumptions, costs, and fill mechanics are not aligned to the target's time-bound evidence and cost-aware evaluation requirements. | Not imported as a candidate or executable strategy. It may be evaluated in a future, separately preregistered experiment after its accounting and assumptions are repaired. |
| [HamidCognition-Unified/PROJECT/llm_fx_eval/eval_gbt_fx.py](https://github.com/hamidhayatijozani/HamidCognition-Unified/blob/main/PROJECT/llm_fx_eval/eval_gbt_fx.py), blob `f22b84e2c04f198c143333fa9b82bcb3913b8ce7` | Daily-rate LLM forecast harness with MAE/MAPE/directional accuracy. Its data frequency and target API contract are different from 1-minute-issue / 5-minute-horizon EUR/USD forecasting. The script also records raw exception text in a CSV field. | Do not merge into the live loop. The target's ClaimLab protocol already specifies temporal controls, preregistration, uncertainty estimation, and explicit costs. Keep the daily harness as historical research until separately adapted and reviewed. |
| [HamidCognition-Unified/SALES/COGNITIVE_FUNDING_MODULE.md](https://github.com/hamidhayatijozani/HamidCognition-Unified/blob/main/SALES/COGNITIVE_FUNDING_MODULE.md), blob `278c1f83a489bde54380d2ac05e50673cbaab599` | Suggests candidate features: normalized volatility, return acceleration, range expansion, tick-volume where available, structural breaks, and multi-timeframe divergence; outputs may include P/S/T, phase, energy and jump-risk measures. | Retain as research hypotheses, not validated signals. The target already has a separate P/S/T-style feature experiment and must not double-count it as new evidence. |
| [HamidCognition-Unified/MIGRATION/CONFLICTS.md](https://github.com/hamidhayatijozani/HamidCognition-Unified/blob/main/MIGRATION/CONFLICTS.md), blob `c1479d539295d3c34254882a0e5a9cd83d577e39` | Identifies duplicate legacy market feeds and significant predictor/P-S-T semantic differences between repositories. | Used as a warning against blind copying; incompatible variants remain separate until behavioral equivalence is demonstrated. |
| [HamidCognition-Unified/broker_runtime/oanda.py](https://github.com/hamidhayatijozani/HamidCognition-Unified/blob/main/broker_runtime/oanda.py), blob `8b50b3d7d3910ba5f95bf33193d6b4f3eee04df1` | OANDA broker/order execution boundary with Action Gate authorization and live-mode controls. | Not imported: the destination is a research and forecasting system, not a broker-order executor. Market data and order execution must remain separate boundaries. |

## 3. Capabilities already present in the target; no duplicate copy created

Inspection of the target's current main branch found these existing pieces:
- `engine/market_providers.py`: normalized Yahoo, OANDA, and Twelve Data candle adapters, configured provider order, complete-candle parsing and failover.
- `engine/trader_sources.py`: public trader/sentiment source manifest and source-refresh evidence.
- `docs/EXTERNAL_CONTEXT.md`, `docs/DEEP_MARKET_BRAIN.md`, and the cross-asset experiments: EURUSD plus GBPUSD, USDJPY and DXY context, with timestamp alignment and preregistered experiments.
- `research/CONSENSUS_CLAIMLAB_PROTOCOL.md` and ClaimLab: frozen-baseline, temporal-validity, data-sufficiency, uncertainty and cost-sensitivity requirements.

Those files are not copied over themselves. The newly imported ranking helper is deliberately **not wired into** `scripts/live_minute_loop.py`, `predict()`, candidate scores, or model weights. Wiring it into the live path requires a new feature version, timestamped evidence contract, an authorized source, and an independently preregistered evaluation.

## 4. Verification boundary

- Repository search: completed against the repositories visible to the linked GitHub account and indexed by GitHub code search; this is not a claim that every private, unindexed, or inaccessible repository was exhaustively searched.
- Files created on this branch: `engine/trader_intelligence.py`, `tests/test_trader_intelligence.py`, and this migration ledger.
- Tests in the new test file: six focused cases covering the time window, symbol/direction/P&L filtering, missing-quality penalties, deterministic ranking cap, bounded consensus, and timestamp/limit validation.
- Test execution and CI for this branch: **UNVERIFIED until GitHub Actions reports a result for the exact branch head**.
- Live trader records/API, trader-source authorization, live integration, incremental predictive value, and profitability: **UNVERIFIED / NOT CLAIMED**.

No source credentials, raw accounts, trader records, or broker execution code were copied.
