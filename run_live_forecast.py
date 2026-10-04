"""One-shot live EUR/USD 5M research forecast."""
from datetime import datetime, timedelta, timezone
from engine.forecast import forecast
from engine.live_feed import latest_complete_window

if __name__=="__main__":
    now=datetime.now(timezone.utc)
    closes=latest_complete_window(now)
    f=forecast(closes)
    target=((now.replace(second=0,microsecond=0)+timedelta(minutes=5)))
    print({
        "created_at":now.isoformat(),
        "target_start":now.isoformat(),
        "target_end":target.isoformat(),
        "instrument":"EURUSD",
        "timeframe":"5m",
        "direction":f.direction,
        "confidence":round(f.confidence,4),
        "regime":f.regime,
        "score":f.score,
        "reference_price":closes[-1],
        "model_version":"baseline-v1",
        "data_source":"Yahoo Finance chart adapter",
    })
