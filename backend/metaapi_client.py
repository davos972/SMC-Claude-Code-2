"""MetaApi client wrapper with explicit degraded mode.

If no token or accountId is configured, methods return an explicit
`MetaApiNotConfiguredError`. We NEVER return simulated price data.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetaApiNotConfiguredError(Exception):
    """Raised when MetaApi token / accountId are not configured."""


class MetaApiConnectionError(Exception):
    """Raised when MetaApi connection fails."""


class MetaApiWrapper:
    """Async wrapper around metaapi-cloud-sdk for the lifetime of the bot."""

    def __init__(self):
        self._token: Optional[str] = None
        self._account_id: Optional[str] = None
        self._api = None
        self._account = None
        self._connection = None
        self._last_error: Optional[str] = None
        self._connected: bool = False
        self._deploying: bool = False
        self._connect_lock = asyncio.Lock()

    def is_configured(self) -> bool:
        return bool(self._token and self._account_id)

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "connected": self._connected,
            "deploying": self._deploying,
            "last_error": self._last_error,
            "account_id": (self._account_id[:6] + "…") if self._account_id else None,
        }

    async def configure(self, token: str, account_id: str) -> None:
        """Update credentials. Disconnects existing connection so next call reconnects."""
        async with self._connect_lock:
            self._token = token.strip() or None
            self._account_id = account_id.strip() or None
            self._last_error = None
            self._connected = False
            self._api = None
            self._account = None
            self._connection = None

    def _require_configured(self) -> None:
        if not self.is_configured():
            raise MetaApiNotConfiguredError(
                "MetaApi credentials not configured. Go to Réglages to add your token and accountId."
            )

    async def _connect(self) -> None:
        """Connect to MetaApi (idempotent). Raises MetaApiConnectionError on failure."""
        self._require_configured()
        if self._connected and self._connection is not None:
            return
        async with self._connect_lock:
            if self._connected and self._connection is not None:
                return
            try:
                from metaapi_cloud_sdk import MetaApi  # type: ignore
                self._api = MetaApi(self._token)
                self._account = await asyncio.wait_for(
                    self._api.metatrader_account_api.get_account(self._account_id),
                    timeout=240.0,
                )
                state = getattr(self._account, "state", None)
                if state and state in ("UNDEPLOYED", "DEPLOYING"):
                    self._deploying = True
                    logger.info("Compte MetaApi non déployé — déploiement en cours, attente jusqu'à 240s…")
                    try:
                        await asyncio.wait_for(self._account.deploy(), timeout=240.0)
                    except Exception as e:
                        logger.warning("deploy() failed: %s", e)
                    self._deploying = False
                try:
                    await asyncio.wait_for(self._account.wait_connected(), timeout=240.0)
                except Exception as e:
                    logger.warning("wait_connected timeout: %s", e)
                self._connection = self._account.get_rpc_connection()
                await asyncio.wait_for(self._connection.connect(), timeout=240.0)
                try:
                    await asyncio.wait_for(self._connection.wait_synchronized(), timeout=240.0)
                except asyncio.TimeoutError:
                    logger.warning("wait_synchronized timeout — proceeding anyway (RPC is usable)")
                self._connected = True
                self._last_error = None
                logger.info("MetaApi connected: %s", self._account_id)
            except Exception as e:
                self._connected = False
                self._last_error = str(e)
                logger.exception("MetaApi connection failed")
                raise MetaApiConnectionError(str(e)) from e

    async def get_account_information(self) -> Dict[str, Any]:
        await self._connect()
        info = await self._connection.get_account_information()
        return info

    async def get_positions(self) -> List[Dict[str, Any]]:
        await self._connect()
        positions = await self._connection.get_positions()
        return positions

    async def get_symbol_price(self, symbol: str) -> Dict[str, Any]:
        await self._connect()
        price = await self._connection.get_symbol_price(symbol)
        return price

    @staticmethod
    def _normalize_timeframe(tf: str) -> str:
        """Map our internal labels (M5, H1, M1, M15) to MetaApi format (5m, 1h, 1m, 15m)."""
        m = {
            "M1": "1m", "M2": "2m", "M3": "3m", "M4": "4m", "M5": "5m",
            "M6": "6m", "M10": "10m", "M12": "12m", "M15": "15m", "M20": "20m",
            "M30": "30m",
            "H1": "1h", "H2": "2h", "H3": "3h", "H4": "4h", "H6": "6h", "H8": "8h", "H12": "12h",
            "D1": "1d", "W1": "1w", "MN1": "1mn",
        }
        if tf in m:
            return m[tf]
        return tf  # already in MetaApi format

    async def get_candles(self, symbol: str, timeframe: str, start_time=None, limit: int = 500) -> List[Dict[str, Any]]:
        """Fetch historical candles via REST endpoint exposed by SDK."""
        await self._connect()
        tf = self._normalize_timeframe(timeframe)
        candles = await self._account.get_historical_candles(symbol, tf, start_time, limit)
        return candles or []

    async def place_order(self, symbol: str, side: str, volume: float, sl: float, tp: float,
                           magic: int = 990077, comment: str = "GFSMC") -> Dict[str, Any]:
        await self._connect()
        opts = {"magic": magic, "comment": comment}
        if side == "buy":
            return await self._connection.create_market_buy_order(
                symbol=symbol, volume=volume, stop_loss=sl, take_profit=tp, options=opts,
            )
        if side == "sell":
            return await self._connection.create_market_sell_order(
                symbol=symbol, volume=volume, stop_loss=sl, take_profit=tp, options=opts,
            )
        raise ValueError("side must be 'buy' or 'sell'")

    async def close_position(self, position_id: str) -> Dict[str, Any]:
        await self._connect()
        return await self._connection.close_position(position_id)

    async def disconnect(self) -> None:
        try:
            if self._connection:
                await self._connection.close()
        except Exception:
            pass
        self._connected = False


# Global singleton, configured at startup from DB
metaapi_client = MetaApiWrapper()
