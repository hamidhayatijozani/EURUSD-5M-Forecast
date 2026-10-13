"""Multi-provider feed adapter with strict closed-candle information lock."""
import json
from datetime import datetime,timedelta,timezone
from statistics import median
from urllib.error import HTTPError
from urllib.request import Request,urlopen

SYMBOLS={"EURUSD":"EURUSD=X","GBPUSD":"GBPUSD=X","USDJPY":"USDJPY=X","DXY":"DX-Y.NYB"}
BASE="https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=5m&range=1d"
BASE_1M="https://query1.finance.yahoo.com/v8/finance/chart/{}?interval=1m&range=1d"

def _validate_live_1m_provider_result(result):
    """Reject unusable one-minute providers before selecting the provider.

    The live forecast contract requires at least 30 contiguous, fully closed
    OHLC candles and a last close no more than 90 seconds old. Doing this
    inside provider selection allows stale or future-dated responses to fall
    through to the next configured source instead of forcing a dead-end HOLD.
    """
    now = datetime.now(timezone.utc)
    timestamps = result.get("timestamp", [])
    quotes = result.get("indicators", {}).get("quote", [])
    if not timestamps or not quotes:
        raise ValueError("missing one-minute OHLC payload")

    quote = quotes[0]
    arrays = [quote.get(key) for key in ("open", "high", "low", "close")]
    if any(not isinstance(values, list) for values in arrays):
        raise ValueError("incomplete one-minute OHLC arrays")

    complete = []
    for index, raw_timestamp in enumerate(timestamps):
        if any(index >= len(values) or values[index] is None for values in arrays):
            continue
        candle_open = datetime.fromtimestamp(float(raw_timestamp), tz=timezone.utc)
        if candle_open + timedelta(minutes=1) <= now:
            complete.append(candle_open)

    if not complete:
        raise ValueError("no closed one-minute OHLC candles")

    latest_close = complete[-1] + timedelta(minutes=1)
    lag_seconds = (now - latest_close).total_seconds()
    if lag_seconds > 90:
        raise ValueError("stale one-minute OHLC candles")

    start = len(complete) - 1
    while start > 0 and complete[start] - complete[start - 1] == timedelta(minutes=1):
        start -= 1
    if len(complete) - start < 30:
        raise ValueError("insufficient contiguous closed one-minute OHLC candles")


def _fetch(symbol,base):
    # Live freshness validation belongs inside provider selection as well as
    # downstream feature checks: a stale first provider must not block fallback.
    from engine.market_providers import fetch_chart_result
    interval = "1m" if base == BASE_1M else "5m"
    if interval == "1m":
        return fetch_chart_result(
            symbol,
            interval,
            SYMBOLS.get(symbol, symbol),
            result_validator=_validate_live_1m_provider_result,
        )
    return fetch_chart_result(symbol, interval, SYMBOLS.get(symbol, symbol))

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
    # Validate the primary stream first; no auxiliary source can compensate
    # for an unusable EURUSD feature window.
    try:
        raw_master=closed_1m_rows("EURUSD",now)
    except Exception as exc:
        if isinstance(exc, HTTPError):
            detail=f"HTTPError:status={exc.code}:reason={exc.reason}"
        else:
            detail=f"{type(exc).__name__}:{exc}"
        raise RuntimeError(f"EURUSD_ONE_MINUTE_FEED_UNAVAILABLE:{detail}") from exc
    if not raw_master:
        raise RuntimeError("EURUSD_ONE_MINUTE_FEED_UNAVAILABLE")
    master_total=len(raw_master)
    master_first=raw_master[0][0]
    master_last=raw_master[-1][0]
    intervals=[(raw_master[i][0]-raw_master[i-1][0]).total_seconds() for i in range(1,len(raw_master))]
    median_interval=median(intervals) if intervals else None
    non_minute_gaps=sum(delta!=60.0 for delta in intervals)
    largest_gap=max(intervals) if intervals else None
    latest_close=master_last+timedelta(minutes=1)
    lag=(now-latest_close).total_seconds()
    if lag>90:
        raise RuntimeError(f"STALE_EURUSD_FEED:{lag:.1f}s")

    start=len(raw_master)-1
    while start>0 and raw_master[start][0]-raw_master[start-1][0]==timedelta(minutes=1):
        start-=1
    master=raw_master[start:][-limit:]
    if len(master)<30:
        raise RuntimeError(
            "INSUFFICIENT_CONTIGUOUS_EURUSD_CANDLES:"
            f"{len(master)}:master_rows={master_total}:first={master_first.isoformat()}:"
            f"last={master_last.isoformat()}:latest_lag_seconds={lag:.1f}:"
            f"median_interval_seconds={median_interval}:non_minute_gaps={non_minute_gaps}:"
            f"largest_gap_seconds={largest_gap}:auxiliary_rows=NOT_FETCHED_PRIMARY_GAP"
        )
    master_times=[row[0] for row in master]
    master_prices=[row[1] for row in master]
    data={"EURUSD":master_prices}
    available_lengths={}

    # Align each auxiliary stream independently. One missing symbol must not
    # suppress valid evidence from the other symbols.
    for symbol in SYMBOLS:
        if symbol=="EURUSD":
            continue
        try:
            aux_rows=closed_1m_rows(symbol,now)
        except Exception:
            aux_rows=[]
        if not aux_rows:
            continue
        aligned,aux_times=_align_asof(
            master,{symbol:aux_rows},max_age=timedelta(minutes=2),limit=limit
        )
        aligned,aux_times=_latest_contiguous(
            aligned,aux_times,step=timedelta(minutes=1)
        )
        if len(aux_times)<30 or not aux_times or aux_times[-1]!=master_times[-1]:
            continue
        mapping={ts:row[1] for ts,row in zip(aux_times,aligned[symbol])}
        available_lengths[symbol]=len(aux_times)
        data[symbol]=mapping

    common_len=min([len(master),*available_lengths.values()]) if available_lengths else len(master)
    times=master_times[-common_len:]
    data={symbol:(values[-common_len:] if symbol=="EURUSD" else [values[ts] for ts in times])
          for symbol,values in data.items()}
    print("CROSS_ASSET_FEED_COVERAGE:"+json.dumps(
        {symbol:len(values) for symbol,values in data.items()},sort_keys=True
    ))
    return data,times


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
