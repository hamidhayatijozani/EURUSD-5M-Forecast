"""Real EUR/USD market ingestion with strict candle validation."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import requests

class MarketIngestionClient:
    def __init__(self, api_endpoint: str, timeout: int = 10, session=None):
        self.api_endpoint=api_endpoint; self.timeout=timeout; self.session=session or requests
    def fetch_latest_eurusd_candle(self) -> Optional[Dict[str, Any]]:
        try:
            response=self.session.get(self.api_endpoint,timeout=self.timeout); response.raise_for_status()
            candle=self._standardize(response.json()); self._validate_candle(candle); return candle
        except (requests.RequestException,KeyError,TypeError,ValueError):
            return None
    @staticmethod
    def _standardize(data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp=data["timestamp"]
        if isinstance(timestamp,(int,float)): timestamp=datetime.fromtimestamp(float(timestamp),tz=timezone.utc).isoformat()
        return {"symbol":"EURUSD","timestamp":str(timestamp),"open":float(data["open"]),"high":float(data["high"]),"low":float(data["low"]),"close":float(data["close"]),"volume":float(data.get("volume",0.0))}
    @staticmethod
    def _validate_candle(candle: Dict[str, Any]) -> None:
        o,h,l,c=(candle[k] for k in ("open","high","low","close"))
        if min(o,h,l,c)<=0: raise ValueError("Non-positive EUR/USD OHLC value")
        if h<l: raise ValueError("High price is lower than low price")
        if not (l<=o<=h and l<=c<=h): raise ValueError("Invalid OHLC spread")
        if candle["symbol"]!="EURUSD": raise ValueError("Unexpected symbol")

class YahooEURUSD5mClient(MarketIngestionClient):
    """Yahoo Finance research adapter, with optional closed-candle selection."""
    def __init__(self,timeout:int=10,session=None):
        super().__init__("https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X?interval=5m&range=1d",timeout=timeout,session=session)
    def fetch_latest_eurusd_candle(self,closed_only:bool=False,now:Optional[datetime]=None)->Optional[Dict[str,Any]]:
        try:
            response=self.session.get(self.api_endpoint,timeout=self.timeout); response.raise_for_status()
            result=response.json()["chart"]["result"][0]; timestamps=result["timestamp"]; quote=result["indicators"]["quote"][0]; rows=[]
            for i,ts in enumerate(timestamps):
                if all(quote[k][i] is not None for k in ("open","high","low","close")):
                    rows.append({"timestamp":datetime.fromtimestamp(ts,tz=timezone.utc).isoformat(),"open":quote["open"][i],"high":quote["high"][i],"low":quote["low"][i],"close":quote["close"][i],"volume":(quote.get("volume") or [0]*len(timestamps))[i] or 0})
            if not rows: return None
            if closed_only:
                current=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
                floor=current.replace(minute=(current.minute//5)*5,second=0,microsecond=0)
                cutoff=floor-timedelta(minutes=5)
                rows=[r for r in rows if datetime.fromisoformat(r["timestamp"]).astimezone(timezone.utc)<=cutoff]
                if not rows: return None
            candle=self._standardize(rows[-1]); self._validate_candle(candle); return candle
        except (requests.RequestException,KeyError,IndexError,TypeError,ValueError):
            return None
