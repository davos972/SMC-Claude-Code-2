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


# Secours UNIQUEMENT si MetaApi est indisponible. Les vraies valeurs sont lues
# en live via get_symbol_specification (tickSize / contractSize) et écrasent
# celles-ci. Spécifications statiques du broker, sans danger comme défaut.
# point_size = taille d'1 point (tickSize) ; contract_size = unités par lot.
_SYMBOL_SPEC_FALLBACK: Dict[str, Dict[str, Any]] = {
    "XAUUSD": {"point_size": 0.01, "contract_size": 100.0, "digits": 2},
    "US30":   {"point_size": 0.1,  "contract_size": 1.0,   "digits": 1},
    "USTECH": {"point_size": 0.1,  "contract_size": 1.0,   "digits": 1},
    "US500":  {"point_size": 0.1,  "contract_size": 1.0,   "digits": 1},
    "GER40":  {"point_size": 0.1,  "contract_size": 1.0,   "digits": 1},
    "_DEFAULT": {"point_size": 0.01, "contract_size": 100.0, "digits": 2},
}


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
        self._spec_cache: Dict[str, Dict[str, Any]] = {}

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

    def _mark_disconnected(self) -> None:
        """Marque la connexion comme perdue → le prochain appel forcera une reconnexion."""
        self._connected = False
        self._connection = None

    async def _rpc_read(self, method: str, *args, timeout: float = 20.0, _retry: bool = True) -> Any:
        """Appel RPC en LECTURE avec délai d'expiration + auto-réparation.

        Cas typique : connexion « zombie » (drapeau connecté mais flux MetaApi
        mort) → l'appel resterait figé indéfiniment. Ici on borne par un timeout ;
        en cas d'expiration/échec on réinitialise la connexion et on retente UNE
        fois. Réservé aux LECTURES — jamais aux ordres, pour ne pas risquer un
        doublon. Échec définitif → MetaApiConnectionError (intercepté par les
        endpoints / la boucle bot) au lieu de rester bloqué."""
        await self._connect()
        try:
            fn = getattr(self._connection, method)
            return await asyncio.wait_for(fn(*args), timeout=timeout)
        except MetaApiNotConfiguredError:
            raise
        except Exception as e:
            self._mark_disconnected()
            if _retry:
                logger.warning("RPC %s en échec (%s) — reconnexion puis nouvelle tentative.",
                               method, type(e).__name__)
                return await self._rpc_read(method, *args, timeout=timeout, _retry=False)
            self._last_error = f"{method}: {e}"
            logger.warning("RPC %s toujours en échec après reconnexion: %s", method, e)
            raise MetaApiConnectionError(self._last_error) from e

    async def get_account_information(self) -> Dict[str, Any]:
        return await self._rpc_read("get_account_information")

    async def get_positions(self) -> List[Dict[str, Any]]:
        return await self._rpc_read("get_positions") or []

    async def get_symbol_price(self, symbol: str) -> Dict[str, Any]:
        return await self._rpc_read("get_symbol_price", symbol)

    async def get_symbol_spec(self, symbol: str) -> Dict[str, Any]:
        """Per-symbol contract specs needed for lot sizing and backtest P&L.

        Returns {point_size, contract_size, digits}. Source of truth = MetaApi
        ``get_symbol_specification`` (tickSize / contractSize), cached for the
        lifetime of the process (these never change intraday). Falls back to a
        small hardcoded table ONLY if MetaApi is unavailable — we never invent
        prices, but contract specs are static broker metadata, safe to default.
        """
        sym = (symbol or "").upper()
        if sym in self._spec_cache:
            return self._spec_cache[sym]
        spec: Optional[Dict[str, Any]] = None
        try:
            raw = await self._rpc_read("get_symbol_specification", symbol)
            tick = float(raw.get("tickSize") or 0) or None
            contract = float(raw.get("contractSize") or 0) or None
            if tick and contract:
                digits = raw.get("digits")
                if digits is None:
                    # derive digits from tick size (0.01 -> 2, 0.1 -> 1, 1 -> 0)
                    import math
                    digits = max(0, int(round(-math.log10(tick)))) if tick < 1 else 0
                spec = {"point_size": tick, "contract_size": contract,
                        "digits": int(digits), "source": "metaapi"}
        except Exception as e:
            logger.warning("get_symbol_spec(%s) MetaApi failed, using fallback: %s", symbol, e)
        if spec is None:
            spec = dict(_SYMBOL_SPEC_FALLBACK.get(sym, _SYMBOL_SPEC_FALLBACK["_DEFAULT"]))
            spec["source"] = "fallback"
        self._spec_cache[sym] = spec
        return spec

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
        try:
            candles = await asyncio.wait_for(
                self._account.get_historical_candles(symbol, tf, start_time, limit),
                timeout=90.0,
            )
        except Exception as e:
            self._mark_disconnected()
            self._last_error = f"get_candles: {e}"
            raise MetaApiConnectionError(self._last_error) from e
        return candles or []

    async def place_order(self, symbol: str, side: str, volume: float, sl: float, tp: float,
                           magic: int = 990077, comment: str = "GFSMC") -> Dict[str, Any]:
        await self._connect()
        opts = {"magic": magic, "comment": comment}
        # Timeout SANS nouvelle tentative : un ordre peut avoir été placé même si
        # la réponse tarde → ne JAMAIS retenter automatiquement (risque de doublon).
        try:
            if side == "buy":
                return await asyncio.wait_for(self._connection.create_market_buy_order(
                    symbol=symbol, volume=volume, stop_loss=sl, take_profit=tp, options=opts,
                ), timeout=30.0)
            if side == "sell":
                return await asyncio.wait_for(self._connection.create_market_sell_order(
                    symbol=symbol, volume=volume, stop_loss=sl, take_profit=tp, options=opts,
                ), timeout=30.0)
        except asyncio.TimeoutError as e:
            self._mark_disconnected()
            self._last_error = "place_order: timeout"
            raise MetaApiConnectionError(self._last_error) from e
        raise ValueError("side must be 'buy' or 'sell'")

    async def close_position(self, position_id: str) -> Dict[str, Any]:
        await self._connect()
        try:
            return await asyncio.wait_for(self._connection.close_position(position_id), timeout=30.0)
        except asyncio.TimeoutError as e:
            self._mark_disconnected()
            self._last_error = "close_position: timeout"
            raise MetaApiConnectionError(self._last_error) from e

    async def modify_position(self, position_id: str, sl: float, tp: float) -> Dict[str, Any]:
        """Modifie le SL/TP d'une position ouverte chez le broker (trailing stop live).
        Timeout 30s, SANS retry (une modification est une écriture : un retry pourrait
        entrer en conflit avec l'évolution du marché)."""
        await self._connect()
        try:
            return await asyncio.wait_for(
                self._connection.modify_position(position_id, stop_loss=sl, take_profit=tp),
                timeout=30.0,
            )
        except asyncio.TimeoutError as e:
            self._mark_disconnected()
            self._last_error = "modify_position: timeout"
            raise MetaApiConnectionError(self._last_error) from e
        except Exception as e:
            self._last_error = f"modify_position: {e}"
            raise MetaApiConnectionError(self._last_error) from e

    async def get_deals_by_position(self, position_id: str) -> List[Dict[str, Any]]:
        """Broker deal history for one position — used to read the REAL realized P&L
        (profit + swap + commission) of a closed trade, instead of inferring it from
        the global account equity delta (which is wrong as soon as several positions
        are open at once). Returns [] if the SDK/connection has no such history."""
        await self._connect()
        if getattr(self._connection, "get_deals_by_position", None) is None:
            return []
        result = await self._rpc_read("get_deals_by_position", position_id)
        if isinstance(result, dict):
            return result.get("deals", []) or []
        return result or []

    async def disconnect(self) -> None:
        try:
            if self._connection:
                await self._connection.close()
        except Exception:
            pass
        self._connected = False


# Global singleton, configured at startup from DB
metaapi_client = MetaApiWrapper()
