"""Public trader/signal source adapters and hourly/24h evidence refresh.

A source becomes a trader only when it exposes timestamped, directionally testable
EUR/USD information. Popularity or lifetime profit is never treated as 5-minute skill.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json, re
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

@dataclass(frozen=True)
class Source:
    source_id:str
    name:str
    url:str
    kind:str

SOURCES=(
    Source("litefinance_social","LiteFinance Social Trading","https://www.litefinance.org/social-trading/","trader"),
    Source("litefinance_blog","LiteFinance Forex Analysis","https://www.litefinance.org/blog/","analysis"),
    Source("forexfactory_eurusd","Forex Factory EUR/USD","https://www.forexfactory.com/market/eurusd","sentiment"),
    Source("myfxbook_eurusd","Myfxbook EURUSD Sentiment","https://www.myfxbook.com/community/outlook/EURUSD","sentiment"),
)

def source_manifest():
    return [asdict(x) for x in SOURCES]

def _get(url,timeout=15):
    req=Request(url,headers={"User-Agent":"EURUSD-5M-Forecast/4.0"})
    with urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8","ignore")

def refresh_public_source_snapshot(path="research/public_sources.json",now=None):
    now=now or datetime.now(timezone.utc)
    rows=[]
    for src in SOURCES:
        try:
            body=_get(src.url)
            rows.append({"source_id":src.source_id,"name":src.name,"url":src.url,
                         "kind":src.kind,"observed_at":now.isoformat(),
                         "ok":True,"bytes":len(body)})
        except Exception as exc:
            rows.append({"source_id":src.source_id,"name":src.name,"url":src.url,
                         "kind":src.kind,"observed_at":now.isoformat(),
                         "ok":False,"error":type(exc).__name__})
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({"refreshed_at":now.isoformat(),"sources":rows},indent=2),encoding="utf-8")
    return rows
