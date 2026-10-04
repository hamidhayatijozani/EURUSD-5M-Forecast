# Live research mode

Run:

    python -m pip install -r requirements.txt
    python run_live_forecast.py

The included adapter reads the public Yahoo Finance chart endpoint for EURUSD=X at 5-minute resolution. It is an adapter, not a claim of a permanent or licensed production feed. Replace it with an authorized provider before commercial deployment.

The adapter filters timestamps to the prediction time and supplies only the latest 12 completed/available closes to the baseline engine. No target candle is injected into the forecast.
