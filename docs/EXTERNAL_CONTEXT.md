# External context fusion

Every minute forecast now has a frozen external-context snapshot in addition to the
closed 1-minute price/cross-asset state.

## Inputs

1. **News and analysis pulse**
   - GDELT DOC API, last 60 minutes.
   - Article timestamps are filtered so an article newer than the forecast candle is
     never used.
   - News tone is a weak directional feature; news volume is stored separately.

2. **Top-50 trader/source leaderboard**
   - The engine accepts immutable third-party forecasts in
     \`research/trader_signals.jsonl\`.
   - Only forecasts whose target has already closed are scored.
   - The ranking window is exactly the preceding 24 hours.
   - Traders are ranked by mean absolute forecast error, with the lowest 50 selected.
   - With fewer than 50 observed traders, the engine records the actual count. It
     does not manufacture missing traders.

3. **Data-center electricity**
   - When \`ELECTRICITY_MAPS_API_KEY\` is present, the engine can read direct
     data-center total-load history using provider/region pairs from
     \`DATACENTER_TARGETS\`.
   - Default targets are \`gcp:europe-west1,gcp:us-central1\`.
   - The load anomaly is a regime/stress feature, not a directional EUR/USD claim.
   - High infrastructure stress reduces conviction rather than forcing UP/DOWN.

4. **Existing market structure**
   - PST / cross-asset pulse / regime gate remain primary.
   - Online calibration remains bounded and evidence-driven.

## Information lock

The forecast timestamp is the latest common closed EUR/USD/GBPUSD/USDJPY/DXY
one-minute candle. External inputs are requested with that timestamp as the cutoff
where the provider permits it. Provider data that cannot be made time-safe is marked
UNAVAILABLE and contributes zero.

This is intentional. A brilliant model with one future byte smuggled into its input
is still a cheating model.
