"""Yahoo research feed adapter with a strict closed-candle information lock."""
import json
from datetime import datetime,timedelta,timezone
from urllib.request import Request,urlopen
SYMBOLS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","DXY":"DX-Y.NYB"}
BASE="https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=5m&range=1d"
def fetch_5m_closes(symbol="EURUSD"):
    req=Request(BASE.format(SYMBOLS.get(symbol,symbol)),headers={"User-Agent":"EURUSD-5M-Forecast/2.0"})
    with urlopen(req,timeout=15) as response: payload=json.load(response)
    result=payload["chart"]["result"][0]
    return [(datetime.fromtimestamp(ts,tz=timezone.utc),float(p)) for ts,p in zip(result["timestamp"],result["indicators"]["quote"][0]["close"]) if p is not None]
def closed_rows(symbol,now=None):
    now=now or datetime.now(timezone.utc)
    rows=fetch_5m_closes() if symbol=="EURUSD" else fetch_5m_closes(symbol)
    return [(ts,p) for ts,p in rows if ts+timedelta(minutes=5)<=now]
def latest_complete_window(now=None):
    rows=closed_rows("EURUSD",now)
    if len(rows)<12: raise RuntimeError("fewer than 12 closed 5m candles")
    return [p for _,p in rows[-12:]]
def aligned_closed_series(now=None,limit=300):
    series={k:closed_rows(k,now) for k in SYMBOLS}
    common=set(ts for ts,_ in series["EURUSD"])
    for k in series: common &= {ts for ts,_ in series[k]}
    times=sorted(common)[-limit:]
    if len(times)<13: raise RuntimeError("fewer than 13 common closed candles")
    maps={k:dict(series[k]) for k in series}
    return {k:[maps[k][ts] for ts in times] for k in series},times
