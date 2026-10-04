"""Public EUR/USD 5-minute feed adapter.

Uses Yahoo Finance chart API as an external research feed. Availability and
terms can change, so production deployments should replace this adapter with
an authorized/licensed feed. No forecast is produced from future candles.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

URL="https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=5m&range=1d"

def fetch_5m_closes() -> list[tuple[datetime,float]]:
    req=Request(URL,headers={"User-Agent":"EURUSD-5M-Forecast/1.0"})
    with urlopen(req,timeout=15) as response:
        payload=json.load(response)
    result=payload["chart"]["result"][0]
    stamps=result["timestamp"]
    closes=result["indicators"]["quote"][0]["close"]
    out=[]
    for ts,close in zip(stamps,closes):
        if close is not None:
            out.append((datetime.fromtimestamp(ts,tz=timezone.utc),float(close)))
    return out

def latest_complete_window(now: datetime|None=None) -> list[float]:
    now=now or datetime.now(timezone.utc)
    rows=fetch_5m_closes()
    complete=[price for ts,price in rows if ts <= now]
    if len(complete)<12:
        raise RuntimeError("live feed returned fewer than 12 usable 5m closes")
    return complete[-12:]
