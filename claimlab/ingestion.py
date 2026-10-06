"""Real EUR/USD market ingestion with strict candle validation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests


class MarketIngestionClient:
    def __init__(self, api_endpoint: str, timeout: int = 10, session=None):
        self.api_endpoint = api_endpoint
        self.timeout = timeout
        self.session = session or requests

    def fetch_latest_eurusd_candle(self) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.get(self.api_endpoint, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            candle = self._standardize(data)
            self._validate_candle(candle)
            return candle
        except (requests.RequestException, KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _standardize(data: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = data["timestamp"]
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
        return {
            "symbol": "EURUSD",
            "timestamp": str(timestamp),
            "open": float(data["open"]),
            "high": float(data["high"]),
            "low": float(data["low"]),
            "close": float(data["close"]),
            "volume": float(data.get("volume", 0.0)),
        }

    @staticmethod
    def _validate_candle(candle: Dict[str, Any]) -> None:
        o, h, l, c = (candle[k] for k in ("open", "high", "low", "close"))
        if min(o, h, l, c) <= 0:
            raise ValueError("Non-positive EUR/USD OHLC value")
        if h < l:
            raise ValueError("High price is lower than low price")
        if not (l <= o <= h and l <= c <= h):
            raise ValueError("Invalid OHLC spread")
        if candle["symbol"] != "EURUSD":
            raise ValueError("Unexpected symbol")


class YahooEURUSD5mClient(MarketIngestionClient):
    """Public Yahoo Finance chart endpoint adapter.

    This is a research data source, not an execution-grade broker feed.
    The response is accepted only after OHLC validation.
    """

    def __init__(self, timeout: int = 10, session=None):
        super().__init__(
            "https://query1.finance.yahoo.com/v8/finance/chart/EURUSD=X"
            "?interval=5m&range=1d",
            timeout=timeout,
            session=session,
        )

    def fetch_latest_eurusd_candle(self) -> Optional[Dict[str, Any]]:
        try:
            response = self.session.get(self.api_endpoint, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            rows = []
            for i, ts in enumerate(timestamps):
                if all(quote[k][i] is not None for k in ("open", "high", "low", "close")):
                    rows.append({
                        "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                        "open": quote["open"][i],
                        "high": quote["high"][i],
                        "low": quote["low"][i],
                        "close": quote["close"][i],
                        "volume": (quote.get("volume") or [0] * len(timestamps))[i] or 0,
                    })
            if not rows:
                return None
            candle = self._standardize(rows[-1])
            self._validate_candle(candle)
            return candle
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None


class GitHubEURUSD5mHistoricalClient:
    """Real EUR/USD 5m OHLCV sample adapter.

    The dataset is historical, not a live quote stream. It is therefore suitable
    for reproducible research ingestion, but it must never be labeled live.
    """

    def __init__(self, timeout: int = 20, session=None):
        self.api_endpoint = (
            "https://raw.githubusercontent.com/getdata-finance/"
            "eurusd-5m-ohlcv-forex-historical-data/main/EURUSD_5m.csv"
        )
        self.timeout = timeout
        self.session = session or requests

    def fetch_latest_eurusd_candle(self) -> Optional[Dict[str, Any]]:
        response = self.session.get(self.api_endpoint, timeout=self.timeout)
        response.raise_for_status()
        text = response.text.decode("utf-8") if isinstance(response.text, bytes) else response.text
        lines = text.strip().splitlines()
        if len(lines) < 2:
            return None
        header = [x.strip() for x in lines[0].split(",")]
        row = [x.strip() for x in lines[-1].split(",")]
        data = dict(zip(header, row))
        candle = {
            "symbol": "EURUSD",
            "timestamp": data["datetime"],
            "open": float(data["open"]),
            "high": float(data["high"]),
            "low": float(data["low"]),
            "close": float(data["close"]),
            "volume": float(data.get("volume", 0.0)),
        }
        self._validate_candle(candle)
        return candle
