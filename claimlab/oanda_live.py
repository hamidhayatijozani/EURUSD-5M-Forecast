"""Authenticated OANDA v20 EUR/USD market-data client.

This module reads prices only. It does not place, modify, or close orders.
Live access requires an eligible OANDA v20 account and API token.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import time
from typing import Any, Iterator

import requests


class OandaConfigurationError(RuntimeError):
    pass


class OandaAPIError(RuntimeError):
    pass


class OandaLiveClient:
    """Fetch or stream account-specific EUR_USD prices from OANDA v20."""

    BASE_URLS = {
        "practice": ("https://api-fxpractice.oanda.com", "https://stream-fxpractice.oanda.com"),
        "live": ("https://api-fxtrade.oanda.com", "https://stream-fxtrade.oanda.com"),
    }

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        environment: str | None = None,
        timeout: float = 10.0,
        session: Any = None,
        stream_session: Any = None,
    ) -> None:
        self.token = token or os.getenv("OANDA_API_TOKEN")
        self.account_id = account_id or os.getenv("OANDA_ACCOUNT_ID")
        self.environment = (environment or os.getenv("OANDA_ENVIRONMENT", "practice")).lower()
        if not self.token or not self.account_id:
            raise OandaConfigurationError(
                "Set OANDA_API_TOKEN and OANDA_ACCOUNT_ID; never commit credentials."
            )
        if self.environment not in self.BASE_URLS:
            raise OandaConfigurationError("OANDA_ENVIRONMENT must be 'practice' or 'live'.")
        if timeout <= 0:
            raise OandaConfigurationError("timeout must be positive")
        self.rest_url, self.stream_url = self.BASE_URLS[self.environment]
        self.timeout = timeout
        self.session = session or requests
        self.stream_session = stream_session or self.session

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Provider timestamp must include a timezone")
        return parsed.astimezone(timezone.utc)

    def get_latest_quote(self, max_age_ms: int = 5000) -> dict[str, Any]:
        """Return a validated real provider quote or raise an explicit error."""
        if max_age_ms < 0:
            raise ValueError("max_age_ms must be non-negative")
        url = f"{self.rest_url}/v3/accounts/{self.account_id}/pricing"
        response = self.session.get(
            url,
            headers=self._headers,
            params={"instruments": "EUR_USD"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        prices = payload.get("prices")
        if not isinstance(prices, list) or not prices:
            raise OandaAPIError("Provider response contained no EUR_USD prices")
        quote = next((item for item in prices if item.get("instrument") == "EUR_USD"), None)
        if quote is None:
            raise OandaAPIError("Provider response did not contain EUR_USD")
        if quote.get("status") not in (None, "tradeable"):
            raise OandaAPIError(f"EUR_USD is not tradeable in the provider response: {quote.get('status')}")
        bids, asks = quote.get("bids"), quote.get("asks")
        if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
            raise OandaAPIError("Provider quote is missing bid/ask levels")
        bid, ask = float(bids[0]["price"]), float(asks[0]["price"])
        if not (0 < bid <= ask):
            raise OandaAPIError("Invalid EUR_USD bid/ask values")
        provider_time = self._parse_timestamp(quote["time"])
        received = datetime.now(timezone.utc)
        age_ms = round((received - provider_time).total_seconds() * 1000)
        raw_hash = sha256(json.dumps(quote, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {
            "provider_id": "oanda_v20",
            "environment": self.environment,
            "instrument": "EUR_USD",
            "symbol": "EURUSD",
            "bid": bid,
            "ask": ask,
            "mid": (bid + ask) / 2.0,
            "provider_event_timestamp_utc": provider_time.isoformat(),
            "received_at_utc": received.isoformat(),
            "event_age_ms": age_ms,
            "freshness_status": "PASS" if 0 <= age_ms <= max_age_ms else "FAIL",
            "raw_payload_hash": raw_hash,
            "request_id": response.headers.get("RequestID"),
            "source_status": quote.get("status", "UNKNOWN"),
        }

    def stream_quotes(self, stop_after: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield real provider price events; caller owns lifecycle/retry policy."""
        if stop_after is not None and stop_after < 1:
            raise ValueError("stop_after must be positive or None")
        url = f"{self.stream_url}/v3/accounts/{self.account_id}/pricing/stream"
        response = self.stream_session.get(
            url,
            headers=self._headers,
            params={"instruments": "EUR_USD", "snapshot": "true"},
            timeout=self.timeout,
            stream=True,
        )
        response.raise_for_status()
        count = 0
        try:
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                event = json.loads(line)
                if event.get("type") == "HEARTBEAT":
                    yield {
                        "provider_id": "oanda_v20",
                        "event_type": "HEARTBEAT",
                        "provider_time_utc": self._parse_timestamp(event["time"]).isoformat(),
                    }
                    continue
                if event.get("type") != "PRICE" or event.get("instrument") != "EUR_USD":
                    continue
                bids, asks = event.get("bids"), event.get("asks")
                if not bids or not asks:
                    raise OandaAPIError("Streaming price event missing bid/ask levels")
                bid, ask = float(bids[0]["price"]), float(asks[0]["price"])
                if not (0 < bid <= ask):
                    raise OandaAPIError("Invalid streamed EUR_USD bid/ask values")
                provider_time = self._parse_timestamp(event["time"])
                received = datetime.now(timezone.utc)
                yield {
                    "provider_id": "oanda_v20",
                    "event_type": "PRICE",
                    "instrument": "EUR_USD",
                    "symbol": "EURUSD",
                    "bid": bid,
                    "ask": ask,
                    "mid": (bid + ask) / 2.0,
                    "provider_event_timestamp_utc": provider_time.isoformat(),
                    "received_at_utc": received.isoformat(),
                    "event_age_ms": round((received - provider_time).total_seconds() * 1000),
                    "raw_payload_hash": sha256(line.encode()).hexdigest(),
                }
                count += 1
                if stop_after is not None and count >= stop_after:
                    return
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
