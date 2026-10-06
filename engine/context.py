"""External context fusion for the live EUR/USD minute engine."""
import json, os, re, urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from urllib.request import Request, urlopen

NEWS_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
POWER_HISTORY_URL = "https://api.electricitymaps.com/v4/total-load/history"

@dataclass(frozen=True)
class ExternalContext:
    news_score: float
    news_volume: float
    trader_score: float
    trader_count: int
    power_score: float
    power_status: str
    context_score: float
    sources: tuple

def _clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, float(x)))

def _fetch_json(url, headers=None, timeout=12):
    req = Request(url, headers=headers or {"User-Agent": "EURUSD-5M-Forecast/3.1"})
    with urlopen(req, timeout=timeout) as r:
        return json.load(r)

def _article_tone(article):
    tone = article.get("tone")
    return _clip(tone / 10.0) if isinstance(tone, (int, float)) else 0.0

def _article_time(article):
    raw = str(article.get("seendate") or article.get("published") or "")
    m = re.search(r"(\d{4})(\d{2})(\d{2})T?(\d{2})(\d{2})(\d{2})", raw)
    if not m:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime(*map(int, m.groups()), tzinfo=timezone.utc)

def fetch_news_context(now=None):
    now = now or datetime.now(timezone.utc)
    params = {
        "query": '(EURUSD OR "EUR/USD" OR euro OR ECB OR "Federal Reserve" OR DXY)',
        "mode": "artlist", "maxrecords": "50", "format": "json", "timespan": "60min",
    }
    try:
        payload = _fetch_json(NEWS_URL + "?" + urllib.parse.urlencode(params))
        articles = [a for a in payload.get("articles", []) if _article_time(a) <= now]
        if not articles:
            return {"score":0.0,"volume":0.0,"count":0,"status":"EMPTY"}
        tones=[_article_tone(a) for a in articles]
        return {"score":_clip(sum(tones)/len(tones)),
                "volume":_clip(len(articles)/25.0),"count":len(articles),"status":"OK"}
    except Exception as exc:
        return {"score":0.0,"volume":0.0,"count":0,"status":f"UNAVAILABLE:{type(exc).__name__}"}

def load_trader_signals(path="research/trader_signals.jsonl", now=None):
    now=now or datetime.now(timezone.utc)
    p=Path(path)
    if not p.exists(): return []
    rows=[]
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            row=json.loads(line)
            pred=datetime.fromisoformat(row["prediction_ts"])
            target=datetime.fromisoformat(row["target_ts"])
            if pred.tzinfo is None: pred=pred.replace(tzinfo=timezone.utc)
            if target.tzinfo is None: target=target.replace(tzinfo=timezone.utc)
            if target <= now: rows.append(row)
        except Exception:
            continue
    return rows

def trader_leaderboard(eurusd_rows, path="research/trader_signals.jsonl", now=None):
    now=now or datetime.now(timezone.utc)
    cutoff=now-timedelta(hours=24)
    price_by_ts={ts:price for ts,price in eurusd_rows}
    by={}
    for row in load_trader_signals(path, now):
        try:
            pred=datetime.fromisoformat(row["prediction_ts"])
            target=datetime.fromisoformat(row["target_ts"])
            if pred.tzinfo is None: pred=pred.replace(tzinfo=timezone.utc)
            if target.tzinfo is None: target=target.replace(tzinfo=timezone.utc)
            if pred < cutoff or target > now: continue
            entry=float(row["entry_price"])
            target_price=row.get("target_price")
            if target_price is None:
                target_price=price_by_ts.get(target)
            if target_price is None: continue
            actual=float(target_price)/entry-1.0
            expected=float(row.get("predicted_return",0.0))
            err=actual-expected
            item=by.setdefault(str(row["trader_id"]),{"trader_id":str(row["trader_id"]),"n":0,"abs_error":[],"signed_error":[]})
            item["n"]+=1; item["abs_error"].append(abs(err)); item["signed_error"].append(err)
        except Exception:
            continue
    ranked=[]
    for item in by.values():
        if item["n"]:
            ranked.append({"trader_id":item["trader_id"],"n":item["n"],
                           "mae":sum(item["abs_error"])/item["n"],
                           "bias":sum(item["signed_error"])/item["n"]})
    ranked.sort(key=lambda x:(x["mae"],-x["n"]))
    top=ranked[:50]
    if not top: return {"score":0.0,"count":0,"leaders":[]}
    weights=[1.0/(x["mae"]+0.00001) for x in top]
    bias=sum(w*x["bias"] for w,x in zip(weights,top))/sum(weights)
    return {"score":_clip(bias/0.0005),"count":len(top),"leaders":top}

def _power_anomaly(values):
    if len(values)<12: return 0.0
    base=median(values[:-1])
    return 0.0 if base==0 else _clip((values[-1]/base-1.0)/0.15)

def _power_targets():
    raw=os.getenv("DATACENTER_TARGETS","gcp:europe-west1,gcp:us-central1")
    return [x.strip().split(":",1) for x in raw.split(",") if ":" in x]

def fetch_power_proxy(token=None, now=None):
    """Direct data-center load where the provider exposes it, with grid fallback.

    This is a measurable infrastructure-stress signal, not a claim that all
    datacenter electricity is observable. It is deliberately low-weight.
    """
    token=token or os.getenv("ELECTRICITY_MAPS_API_KEY")
    now=now or datetime.now(timezone.utc)
    if not token:
        return {"score":0.0,"status":"UNAVAILABLE:NO_API_KEY","targets":[]}
    headers={"User-Agent":"EURUSD-5M-Forecast/3.1","auth-token":token}
    scores=[]; targets=[]
    for provider,region in _power_targets():
        try:
            params={"dataCenterProvider":provider,"dataCenterRegion":region,
                    "temporalGranularity":"5_minutes"}
            payload=_fetch_json(POWER_HISTORY_URL+"?"+urllib.parse.urlencode(params),headers)
            vals=[]
            for x in payload.get("history",[]):
                ts=x.get("datetime")
                if not ts: continue
                dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
                if dt <= now and isinstance(x.get("value"),(int,float)):
                    vals.append(float(x["value"]))
            if len(vals)>=12:
                scores.append(_power_anomaly(vals)); targets.append(f"{provider}:{region}")
        except Exception:
            continue
    if not scores:
        return {"score":0.0,"status":"UNAVAILABLE:PROVIDER","targets":[]}
    return {"score":sum(scores)/len(scores),"status":"OK","targets":targets}

def fuse_context(news,traders,power):
    # News and observed trader error are directional. Data-center load is a
    # stress/regime feature and is intentionally not treated as direction.
    directional=_clip(0.55*news["score"]+0.45*traders["score"])
    return ExternalContext(news_score=news["score"],news_volume=news.get("volume",0.0),
        trader_score=traders["score"],trader_count=traders["count"],
        power_score=power["score"],power_status=power["status"],
        context_score=directional,
        sources=("GDELT","TRADER_LEADERBOARD_24H","ELECTRICITY_MAPS_DATACENTER_LOAD"))

def collect_external_context(eurusd_rows,now=None):
    now=now or datetime.now(timezone.utc)
    return asdict(fuse_context(fetch_news_context(now),
        trader_leaderboard(eurusd_rows,now=now),fetch_power_proxy(now=now)))
