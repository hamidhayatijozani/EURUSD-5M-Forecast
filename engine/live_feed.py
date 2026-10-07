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

def _align_asof(master, series, *, max_age, limit):
    """Align auxiliary quotes to EURUSD timestamps using past data only."""
    ordered={k:sorted(v,key=lambda row:row[0]) for k,v in series.items()}
    pointers={k:0 for k in ordered}
    aligned={k:[] for k in ordered}
    times=[]
    for master_row in master:
        ts=master_row[0]
        selected={}
        valid=True
        for symbol,rows in ordered.items():
            if not rows:
                valid=False
                break
            j=pointers[symbol]
            while j+1<len(rows) and rows[j+1][0] <= ts:
                j+=1
            pointers[symbol]=j
            row=rows[j]
            # Never use a future quote; reject stale context rather than invent it.
            if row[0] > ts or ts-row[0] > max_age:
                valid=False
                break
            selected[symbol]=row
        if not valid:
            continue
        times.append(ts)
        for symbol,row in selected.items():
            aligned[symbol].append(row)
    if limit:
        times=times[-limit:]
        aligned={k:v[-limit:] for k,v in aligned.items()}
    return aligned,times


def _latest_contiguous(aligned, times, *, step):
    """Keep only the newest uninterrupted cadence to preserve target horizons."""
    if not times:
        return {k:[] for k in aligned},[]
    start=len(times)-1
    while start>0 and times[start]-times[start-1]==step:
        start-=1
    return {k:v[start:] for k,v in aligned.items()},times[start:]


def aligned_closed_series(now=None,limit=300):
    series={k:closed_rows(k,now) for k in SYMBOLS}
    master=series["EURUSD"]
    aligned,times=_align_asof(
        master,series,max_age=timedelta(minutes=15),limit=limit
    )
    aligned,times=_latest_contiguous(aligned,times,step=timedelta(minutes=5))
    if len(times)<13:
        raise RuntimeError("fewer than 13 fresh past-aligned closed 5m candles")
    return {k:[row[1] for row in aligned[k]] for k in aligned},times

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
    now=now or datetime.now(timezone.utc)
    series={}
    for symbol in SYMBOLS:
        try:
            series[symbol]=closed_1m_rows(symbol,now)
        except Exception:
            series[symbol]=[]
    master=series.get("EURUSD",[])
    if not master:
        raise RuntimeError("EURUSD_ONE_MINUTE_FEED_UNAVAILABLE")
    latest_close=master[-1][0]+timedelta(minutes=1)
    lag=(now-latest_close).total_seconds()
    if lag>90:
        raise RuntimeError(f"STALE_EURUSD_FEED:{lag:.1f}s")

    aligned,times=_align_asof(
        master,series,max_age=timedelta(minutes=10),limit=limit
    )
    aligned,times=_latest_contiguous(aligned,times,step=timedelta(minutes=1))
    if len(times)>=30 and all(len(aligned.get(k,[]))==len(times) for k in SYMBOLS):
        return {k:[row[1] for row in aligned[k]] for k in aligned},times

    # Explicit EURUSD-only fallback: no stale or fabricated cross-asset values.
    start=len(master)-1
    while start>0 and master[start][0]-master[start-1][0]==timedelta(minutes=1):
        start-=1
    master=master[start:][-limit:]
    times=[row[0] for row in master]
    if len(times)<30:
        raise RuntimeError(f"INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES:{len(times)}")
    return {"EURUSD":[row[1] for row in master]},times

def aligned_closed_1m_ohlc(now=None,limit=120):
    now=now or datetime.now(timezone.utc)
    rows=[row for row in fetch_1m_ohlc("EURUSD")
          if row[0]+timedelta(minutes=1)<=now]
    if not rows:
        raise RuntimeError("EURUSD_ONE_MINUTE_OHLC_UNAVAILABLE")
    latest_close=rows[-1][0]+timedelta(minutes=1)
    lag=(now-latest_close).total_seconds()
    if lag>90:
        raise RuntimeError(f"STALE_EURUSD_OHLC_FEED:{lag:.1f}s")
    start=len(rows)-1
    while start>0 and rows[start][0]-rows[start-1][0]==timedelta(minutes=1):
        start-=1
    rows=rows[start:][-limit:]
    if len(rows)<30:
        raise RuntimeError(f"INSUFFICIENT_CONTIGUOUS_EURUSD_OHLC:{len(rows)}")
    return {"EURUSD":[row[1:] for row in rows]},[row[0] for row in rows]
