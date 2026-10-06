"""Yahoo research feed adapter with strict closed-candle information lock."""
import json
from datetime import datetime,timedelta,timezone
from urllib.request import Request,urlopen

SYMBOLS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","DXY":"DX-Y.NYB"}
BASE="https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=5m&range=1d"
BASE_1M="https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1m&range=1d"

def _fetch(symbol,base):
    req=Request(base.format(SYMBOLS.get(symbol,symbol)),headers={"User-Agent":"EURUSD-5M-Forecast/3.0"})
    with urlopen(req,timeout=15) as response: payload=json.load(response)
    return payload["chart"]["result"][0]

def fetch_5m_closes(symbol="EURUSD"):
    r=_fetch(symbol,BASE)
    return [(datetime.fromtimestamp(ts,tz=timezone.utc),float(p)) for ts,p in
            zip(r["timestamp"],r["indicators"]["quote"][0]["close"]) if p is not None]

def closed_rows(symbol,now=None):
    now=now or datetime.now(timezone.utc)
    return [(ts,p) for ts,p in fetch_5m_closes(symbol) if ts+timedelta(minutes=5)<=now]

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

def fetch_1m_ohlc(symbol="EURUSD"):
    r=_fetch(symbol,BASE_1M)
    q=r["indicators"]["quote"][0]
    rows=[]
    for i,ts in enumerate(r["timestamp"]):
        vals=[q.get(k,[None])[i] for k in ("open","high","low","close")]
        if all(v is not None for v in vals):
            rows.append((datetime.fromtimestamp(ts,tz=timezone.utc),*map(float,vals)))
    return rows

def closed_1m_rows(symbol="EURUSD",now=None):
    now=now or datetime.now(timezone.utc)
    return [(ts,c) for ts,o,h,l,c in fetch_1m_ohlc(symbol)
            if ts+timedelta(minutes=1)<=now]

def aligned_closed_1m_series(now=None,limit=120):
    series={k:closed_1m_rows(k,now) for k in SYMBOLS}
    common=set(ts for ts,_ in series["EURUSD"])
    for k in series: common &= {ts for ts,_ in series[k]}
    times=sorted(common)[-limit:]
    if len(times)<13: raise RuntimeError("fewer than 13 common closed one-minute candles")
    maps={k:dict(series[k]) for k in series}
    return {k:[maps[k][ts] for ts in times] for k in series},times

def aligned_closed_1m_ohlc(now=None,limit=120):
    series={k:fetch_1m_ohlc(k) for k in SYMBOLS}
    now=now or datetime.now(timezone.utc)
    closed={k:[row for row in rows if row[0]+timedelta(minutes=1)<=now] for k,rows in series.items()}
    common=set(ts for ts,*_ in closed["EURUSD"])
    for k in closed: common &= {ts for ts,*_ in closed[k]}
    times=sorted(common)[-limit:]
    if len(times)<13: raise RuntimeError("fewer than 13 common closed one-minute OHLC candles")
    maps={k:{row[0]:row[1:] for row in closed[k]} for k in closed}
    return {k:[maps[k][ts] for ts in times] for k in maps},times
