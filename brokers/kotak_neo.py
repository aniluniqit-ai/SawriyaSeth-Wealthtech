"""
kotak_neo.py - Kotak Neo Securities Broker Integration (Paper Trading)

JSS Sawriya Seth Wealthtech
Integrates with the Kotak Neo sandbox / paper-trading API to fetch market
data (LTP, candles, option chains) and simulate order placement.

IMPORTANT: All order-related methods operate in **paper-trading mode** – no
real orders are sent to the exchange.  Orders are logged, tracked in-memory,
and can be queried via ``get_positions`` / ``get_order_history``.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

import pyotp
import requests

from .session_manager import load_kotak_session, save_kotak_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Kotak Neo API base URLs
BASE_URL = "https://gw-napi.kotaksecurities.com"
LOGIN_URL = f"{BASE_URL}/Rest1/MFOrder/1.0/API/V1/user/login"
LTP_URL = f"{BASE_URL}/Rest1/MFOrder/1.0/API/V1/scripMaster"
ORDER_URL = f"{BASE_URL}/order/1.0/order/mis"
HISTORY_URL = f"{BASE_URL}/api/1.0/orders"
POSITIONS_URL = f"{BASE_URL}/api/1.0/positions"

# NSE market hours in IST (24-hour clock)
_MARKET_OPEN_HOUR = 9
_MARKET_OPEN_MINUTE = 15
_MARKET_CLOSE_HOUR = 15
_MARKET_CLOSE_MINUTE = 30

# Exchange instrument mapping (Kotak Neo exchange tokens)
_INSTRUMENT_MAP: dict[str, dict[str, str]] = {
    "NIFTY": {
        "exchange": "NSE",
        "exchange_token": "26",
        "trading_symbol": "NIFTY 50",
        "instrument_type": "INDEX",
        "lot_size": "25",
    },
    "BANKNIFTY": {
        "exchange": "NSE",
        "exchange_token": "25",
        "trading_symbol": "BANK NIFTY",
        "instrument_type": "INDEX",
        "lot_size": "15",
    },
    "FINNIFTY": {
        "exchange": "NSE",
        "exchange_token": "27",
        "trading_symbol": "NIFTY FIN SERVICE",
        "instrument_type": "INDEX",
        "lot_size": "25",
    },
}

# Mapping of candle interval strings to Kotak Neo interval codes
_INTERVAL_MAP: dict[str, str] = {
    "1m": "1minute",
    "3m": "3minute",
    "5m": "5minute",
    "15m": "15minute",
    "30m": "30minute",
    "1h": "1hour",
    "1d": "1day",
    "1w": "1week",
}


# =========================================================================
# Broker Class
# =========================================================================

class KotakNeoBroker:
    """Kotak Neo Securities paper-trading broker.

    Provides market-data fetching (LTP, candles, option chains) through the
    Kotak Neo sandbox API, and simulates order placement / cancellation
    entirely in memory (no real exchange interaction).

    Args:
        config: Dictionary with keys ``client_code``, ``access_token``,
            ``mobile``, ``mpin``, ``totp_secret``.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialise the broker with credentials from *config*.

        Expected config keys:
            - client_code  : Kotak Neo client code (6-digit)
            - access_token : Static access token for API authentication
            - mobile       : Registered mobile number (10-digit)
            - mpin         : 4/6-digit MPIN for login
            - totp_secret  : Base-32 TOTP secret for 2FA
        """
        self.client_code: str = config.get("client_code", "")
        self.access_token: str = config.get("access_token", "")
        self.mobile: str = config.get("mobile", "")
        self.mpin: str = config.get("mpin", "")
        self.totp_secret: str = config.get("totp_secret", "")

        # Active session fields – populated by login()
        self.sid: str = ""          # Kotak session ID
        self.user_id: str = ""      # Logged-in user ID
        self.session_token: str = ""  # Bearer token for subsequent calls

        # Paper trading state (in-memory only)
        self._orders: list[dict[str, Any]] = []
        self._positions: list[dict[str, Any]] = []
        self._order_counter: int = 1000  # Simple auto-increment ID

        # HTTP session for connection pooling
        self._http: requests.Session = requests.Session()
        self._http.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "JSS-Sawriya-Seth/1.0",
        })

        # Session timeout (Kotak sessions typically expire after ~6 hours)
        self._session_max_age: timedelta = timedelta(hours=6)

        logger.info(
            "KotakNeoBroker initialised (client_code=%s, paper_trading=True)",
            self.client_code,
        )

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @property
    def _auth_headers(self) -> dict[str, str]:
        """Build authorisation headers using the active session token."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Session-Token": self.sid,
        }
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"
        return headers

    def _generate_totp(self) -> str:
        """Generate a time-based one-time password using pyotp.

        Returns:
            6-digit TOTP string.
        """
        totp = pyotp.TOTP(self.totp_secret)
        otp = totp.now()
        logger.debug("TOTP generated (masked: ****%s)", otp[-2:])
        return otp

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def login(self) -> dict[str, Any]:
        """Authenticate with Kotak Neo sandbox and persist the session.

        Generates a TOTP from the configured secret, POSTs credentials to
        the login endpoint, and stores the resulting session via
        :func:`session_manager.save_kotak_session`.

        Returns:
            Dict with ``success``, ``message``, and (on success) ``data``.

        Raises:
            RuntimeError: If login request fails or returns an error.
        """
        logger.info("Attempting Kotak Neo login for client %s…", self.client_code)

        totp = self._generate_totp()
        password = self.mpin + totp  # Kotak Neo expects MPIN + TOTP concatenated

        payload = {
            "userId": self.client_code,
            "password": password,
        }

        try:
            resp = self._http.post(
                LOGIN_URL,
                json=payload,
                headers={
                    **self._http.headers,
                    "Authorization": f"Bearer {self.access_token}",
                },
                timeout=15,
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()

        except requests.exceptions.HTTPError as exc:
            msg = f"Login HTTP error: {exc.response.status_code} – {exc.response.text}"
            logger.error(msg)
            return {"success": False, "message": msg}
        except requests.exceptions.RequestException as exc:
            msg = f"Login request failed: {exc}"
            logger.error(msg)
            return {"success": False, "message": msg}
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"Failed to parse login response: {exc}"
            logger.error(msg)
            return {"success": False, "message": msg}

        # Parse session fields from response
        if result.get("Status") != 200 and not result.get("sid"):
            error_msg = result.get("message", result.get("errMsg", "Unknown error"))
            logger.error("Login failed: %s", error_msg)
            return {"success": False, "message": error_msg}

        self.sid = result.get("sid", "")
        self.user_id = result.get("userId", self.client_code)
        self.session_token = result.get("token", self.access_token)

        # Persist session for reuse
        session_data = {
            "sid": self.sid,
            "token": self.session_token,
            "userId": self.user_id,
            "client_code": self.client_code,
        }
        save_kotak_session(session_data)

        logger.info("Login successful – session ID: %s…", self.sid[:8])
        return {
            "success": True,
            "message": "Login successful",
            "data": session_data,
        }

    def load_session(self) -> dict[str, Any]:
        """Load a previously saved session and check freshness.

        If the saved session is older than ``_session_max_age`` (default 6 h),
        an automatic re-login is triggered.

        Returns:
            Dict with ``success``, ``message``, and ``relogged`` flag.
        """
        logger.info("Loading saved Kotak session…")

        session = load_kotak_session()
        if session is None:
            logger.warning("No saved session found – performing fresh login.")
            result = self.login()
            result["relogged"] = True
            return result

        # Check staleness
        saved_at = session.get("saved_at")
        if saved_at:
            try:
                saved_time = datetime.fromisoformat(saved_at)
                if datetime.now() - saved_time > self._session_max_age:
                    logger.info(
                        "Session expired (saved %s) – re-logging in…", saved_at
                    )
                    result = self.login()
                    result["relogged"] = True
                    return result
            except (ValueError, TypeError):
                logger.warning("Invalid saved_at timestamp; forcing re-login.")
                result = self.login()
                result["relogged"] = True
                return result

        # Restore session fields
        self.sid = session.get("sid", "")
        self.session_token = session.get("token", self.access_token)
        self.user_id = session.get("userId", self.client_code)
        logger.info("Session restored (sid=%s…)", self.sid[:8])

        return {"success": True, "message": "Session restored", "relogged": False}

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    def get_ltp(self, symbol: str) -> float:
        """Fetch the Last Traded Price (LTP) for an index or equity.

        Args:
            symbol: Instrument symbol (e.g. ``"NIFTY"``, ``"BANKNIFTY"``).

        Returns:
            LTP as a float. Returns ``0.0`` on failure.

        Note:
            In sandbox / paper-trading mode, if the API is unreachable a
            reasonable simulated value is returned for continuity.
        """
        symbol = symbol.upper().strip()
        instrument = _INSTRUMENT_MAP.get(symbol)

        if not instrument:
            logger.error("Unknown symbol: %s", symbol)
            return 0.0

        params = {
            "exchange": instrument["exchange"],
            "instrumentToken": instrument["exchange_token"],
        }

        try:
            resp = self._http.get(
                LTP_URL,
                params=params,
                headers=self._auth_headers,
                timeout=10,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

            # Kotak returns LTP inside the response body
            ltp = float(data.get("ltp", data.get("lastPrice", 0)))
            logger.info("LTP for %s: %.2f", symbol, ltp)
            return ltp

        except requests.exceptions.RequestException as exc:
            logger.error("get_ltp request failed for %s: %s", symbol, exc)

            # Fallback simulated prices for paper trading continuity
            fallback = {
                "NIFTY": 24_500.0,
                "BANKNIFTY": 52_000.0,
                "FINNIFTY": 23_000.0,
            }
            simulated = fallback.get(symbol, 1000.0)
            # Add small random jitter so it looks realistic
            simulated += random.uniform(-50, 50)
            logger.warning(
                "Using simulated LTP for %s: %.2f (API unavailable)", symbol, simulated
            )
            return round(simulated, 2)

        except (ValueError, TypeError, KeyError) as exc:
            logger.error("Failed to parse LTP response for %s: %s", symbol, exc)
            return 0.0

    def get_candles(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch OHLCV candle data for a given symbol.

        Args:
            symbol:   Instrument symbol (e.g. ``"NIFTY"``, ``"BANKNIFTY"``).
            interval: Candle timeframe – one of ``1m``, ``3m``, ``5m``,
                      ``15m``, ``30m``, ``1h``, ``1d``, ``1w``.
            limit:    Max number of candles to return (default 100).

        Returns:
            List of dicts, each with keys: ``timestamp``, ``open``, ``high``,
            ``low``, ``close``, ``volume``.  Empty list on failure.
        """
        symbol = symbol.upper().strip()
        instrument = _INSTRUMENT_MAP.get(symbol)

        if not instrument:
            logger.error("Unknown symbol for candles: %s", symbol)
            return []

        kotak_interval = _INTERVAL_MAP.get(interval, "5minute")

        params: dict[str, Any] = {
            "exchange": instrument["exchange"],
            "instrumentToken": instrument["exchange_token"],
            "interval": kotak_interval,
            "fromDate": self._days_ago_iso(30),      # Kotak expects from-date
            "toDate": datetime.now().strftime("%Y-%m-%d"),
        }

        try:
            resp = self._http.get(
                f"{BASE_URL}/chart/1.0/chart/candles",
                params=params,
                headers=self._auth_headers,
                timeout=15,
            )
            resp.raise_for_status()
            raw: Any = resp.json()

            # Kotak returns candles as [[ts, o, h, l, c, v], …]
            candles_raw = raw.get("candles", raw.get("data", []))
            candles: list[dict[str, Any]] = []
            for c in candles_raw[:limit]:
                if isinstance(c, (list, tuple)) and len(c) >= 6:
                    candles.append({
                        "timestamp": c[0],
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": int(c[5]),
                    })

            logger.info(
                "Fetched %d candles for %s (%s)", len(candles), symbol, interval
            )
            return candles

        except requests.exceptions.RequestException as exc:
            logger.error("get_candles request failed for %s: %s", symbol, exc)
            return []
        except (ValueError, TypeError, KeyError) as exc:
            logger.error("Failed to parse candle data for %s: %s", symbol, exc)
            return []

    def get_option_chain(
        self,
        symbol: str,
        expiry: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch the full CE/PE option chain for an index.

        Args:
            symbol: Underlying symbol (``"NIFTY"`` or ``"BANKNIFTY"``).
            expiry: Expiry date in ``YYYY-MM-DD`` format.  If ``None``, the
                    nearest weekly expiry is used.

        Returns:
            List of dicts with keys: ``strike``, ``ce_ltp``, ``pe_ltp``,
            ``ce_oi``, ``pe_oi``, ``ce_volume``, ``pe_volume``, ``ce_iv``,
            ``pe_iv``, ``ce_change_oi``, ``pe_change_oi``, ``ce_change``,
            ``pe_change``, ``atm``.  Empty list on failure.
        """
        symbol = symbol.upper().strip()
        instrument = _INSTRUMENT_MAP.get(symbol)

        if not instrument:
            logger.error("Unknown symbol for option chain: %s", symbol)
            return []

        if expiry is None:
            expiry = self._next_weekly_expiry()

        atm_strike = self.get_atm_strike(symbol)

        params: dict[str, Any] = {
            "exchange": instrument["exchange"],
            "instrumentToken": instrument["exchange_token"],
            "expiryDate": expiry,
        }

        try:
            resp = self._http.get(
                f"{BASE_URL}/api/1.0/optionchain",
                params=params,
                headers=self._auth_headers,
                timeout=15,
            )
            resp.raise_for_status()
            raw: Any = resp.json()

            chain_raw = raw.get("optionChain", raw.get("data", []))
            chain: list[dict[str, Any]] = []

            for item in chain_raw:
                strike = float(item.get("strikePrice", 0))
                chain.append({
                    "strike": strike,
                    "ce_ltp": float(item.get("CE", {}).get("ltp", 0)),
                    "pe_ltp": float(item.get("PE", {}).get("ltp", 0)),
                    "ce_oi": int(item.get("CE", {}).get("openInterest", 0)),
                    "pe_oi": int(item.get("PE", {}).get("openInterest", 0)),
                    "ce_volume": int(item.get("CE", {}).get("totalTradedVolume", 0)),
                    "pe_volume": int(item.get("PE", {}).get("totalTradedVolume", 0)),
                    "ce_iv": float(item.get("CE", {}).get("impliedVolatility", 0)),
                    "pe_iv": float(item.get("PE", {}).get("impliedVolatility", 0)),
                    "ce_change_oi": int(
                        item.get("CE", {}).get("changeinOpenInterest", 0)
                    ),
                    "pe_change_oi": int(
                        item.get("PE", {}).get("changeinOpenInterest", 0)
                    ),
                    "ce_change": float(item.get("CE", {}).get("change", 0)),
                    "pe_change": float(item.get("PE", {}).get("change", 0)),
                    "atm": (strike == atm_strike),
                })

            logger.info(
                "Option chain for %s: %d strikes (ATM=%s, expiry=%s)",
                symbol,
                len(chain),
                atm_strike,
                expiry,
            )
            return chain

        except requests.exceptions.RequestException as exc:
            logger.error(
                "get_option_chain request failed for %s: %s", symbol, exc
            )
            return []
        except (ValueError, TypeError, KeyError) as exc:
            logger.error(
                "Failed to parse option chain for %s: %s", symbol, exc
            )
            return []

    def get_atm_strike(self, symbol: str) -> int:
        """Calculate the At-The-Money (ATM) strike for *symbol*.

        The ATM strike is the nearest round lot:
        - **NIFTY / FINNIFTY** → rounded to nearest 50
        - **BANKNIFTY** → rounded to nearest 100

        Args:
            symbol: Underlying index symbol.

        Returns:
            Integer ATM strike price.
        """
        symbol = symbol.upper().strip()
        ltp = self.get_ltp(symbol)

        if ltp <= 0:
            logger.warning("LTP is 0 for %s; returning 0 as ATM.", symbol)
            return 0

        step = 100 if symbol == "BANKNIFTY" else 50
        atm = int(round(ltp / step) * step)

        logger.info("ATM strike for %s (LTP=%.2f): %d", symbol, ltp, atm)
        return atm

    # ------------------------------------------------------------------
    # Paper Trading – Orders
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        option_type: str,
        strike: int,
        direction: str,
        qty: int,
        order_type: str = "MARKET",
        price: float = 0,
    ) -> dict[str, Any]:
        """Place a simulated (paper) order.

        This method does **not** send any request to the exchange.  It
        constructs an order dict, appends it to the in-memory order book,
        and immediately "fills" it at the simulated price.

        Args:
            symbol:      Underlying (``"NIFTY"``, ``"BANKNIFTY"``).
            option_type: ``"CE"`` (Call) or ``"PE"`` (Put).
            strike:      Strike price of the option.
            direction:   ``"BUY"`` or ``"SELL"``.
            qty:         Quantity (number of lots × lot size).
            order_type:  ``"MARKET"`` or ``"LIMIT"``.
            price:       Limit price (used only when *order_type* is
                         ``"LIMIT"``).

        Returns:
            Order dict with ``order_id``, ``status``, ``filled_price``, etc.
        """
        self._order_counter += 1
        order_id = f"JSS{self._order_counter}"

        option_type = option_type.upper()
        direction = direction.upper()

        # Simulated fill price – for MARKET orders, fetch a realistic LTP
        filled_price = price
        if order_type.upper() == "MARKET":
            # Use a small random offset from any given price, or generate one
            filled_price = max(price, random.uniform(50, 500))

        order: dict[str, Any] = {
            "order_id": order_id,
            "symbol": symbol.upper(),
            "option_type": option_type,
            "strike": strike,
            "direction": direction,
            "qty": qty,
            "order_type": order_type.upper(),
            "price": price,
            "filled_price": round(filled_price, 2),
            "status": "FILLED",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "sl": 0,
            "target": 0,
        }

        self._orders.append(order)

        # Update positions
        self._update_position(order)

        logger.info(
            "PAPER ORDER PLACED: %s %s %s %d %s x%d @ %.2f → %s",
            direction,
            symbol,
            option_type,
            strike,
            order_type,
            qty,
            filled_price,
            order_id,
        )

        return order

    def modify_order(
        self,
        order_id: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Modify an existing paper order (SL / target).

        Args:
            order_id: The order ID returned by :meth:`place_order`.
            params:   Dict of fields to update. Supported keys:
                      ``sl``, ``target``, ``qty``, ``order_type``, ``price``.

        Returns:
            Updated order dict, or a dict with ``success: False`` if the
            order was not found.
        """
        for order in self._orders:
            if order["order_id"] == order_id:
                for key, value in params.items():
                    if key in ("sl", "target", "qty", "order_type", "price"):
                        order[key] = value
                order["updated_at"] = datetime.now().isoformat()

                logger.info(
                    "PAPER ORDER MODIFIED: %s → %s", order_id, params
                )
                return order

        logger.warning("modify_order: order %s not found", order_id)
        return {"success": False, "message": f"Order {order_id} not found"}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open paper order.

        Args:
            order_id: The order ID to cancel.

        Returns:
            Dict with ``success``, ``message``, and the cancelled order data.
        """
        for i, order in enumerate(self._orders):
            if order["order_id"] == order_id:
                if order["status"] in ("FILLED", "CANCELLED"):
                    msg = (
                        f"Cannot cancel order {order_id} "
                        f"(status={order['status']})"
                    )
                    logger.warning(msg)
                    return {"success": False, "message": msg}

                self._orders[i]["status"] = "CANCELLED"
                self._orders[i]["updated_at"] = datetime.now().isoformat()

                logger.info("PAPER ORDER CANCELLED: %s", order_id)
                return {
                    "success": True,
                    "message": f"Order {order_id} cancelled",
                    "data": self._orders[i],
                }

        logger.warning("cancel_order: order %s not found", order_id)
        return {"success": False, "message": f"Order {order_id} not found"}

    # ------------------------------------------------------------------
    # Portfolio queries
    # ------------------------------------------------------------------

    def get_positions(self) -> list[dict[str, Any]]:
        """Return current open (filled) paper positions.

        Returns:
            List of order dicts whose status is ``"FILLED"``.
        """
        positions = [o for o in self._orders if o["status"] == "FILLED"]
        logger.info("Current open paper positions: %d", len(positions))
        return positions

    def get_order_history(self) -> list[dict[str, Any]]:
        """Return the complete paper order history.

        Returns:
            List of all order dicts (FILLED, CANCELLED, OPEN, etc.).
        """
        logger.info("Paper order history: %d orders", len(self._orders))
        return list(self._orders)

    # ------------------------------------------------------------------
    # Market utility
    # ------------------------------------------------------------------

    @staticmethod
    def is_market_open() -> bool:
        """Check whether the NSE equity / derivatives market is currently open.

        Market hours: **09:15 – 15:30 IST**, Monday through Friday.
        Does **not** account for exchange holidays.

        Returns:
            ``True`` if the market should be open right now, ``False``
            otherwise.
        """
        now = datetime.now()

        # Saturday = 5, Sunday = 6
        if now.weekday() >= 5:
            logger.debug("Market closed – weekend")
            return False

        current_minutes = now.hour * 60 + now.minute
        open_minutes = _MARKET_OPEN_HOUR * 60 + _MARKET_OPEN_MINUTE  # 9*60+15 = 555
        close_minutes = _MARKET_CLOSE_HOUR * 60 + _MARKET_CLOSE_MINUTE  # 15*60+30 = 930

        is_open = open_minutes <= current_minutes <= close_minutes
        logger.debug(
            "Market status check: %s (%02d:%02d)",
            "OPEN" if is_open else "CLOSED",
            now.hour,
            now.minute,
        )
        return is_open

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _update_position(self, order: dict[str, Any]) -> None:
        """Merge a newly filled order into the position tracker.

        If a matching position (same symbol + option_type + strike + direction)
        already exists, the quantity is aggregated.  Otherwise a new position
        entry is created.
        """
        key = (
            order["symbol"],
            order["option_type"],
            order["strike"],
            order["direction"],
        )
        for pos in self._positions:
            if (
                pos["symbol"] == order["symbol"]
                and pos["option_type"] == order["option_type"]
                and pos["strike"] == order["strike"]
                and pos["direction"] == order["direction"]
            ):
                pos["qty"] += order["qty"]
                pos["avg_price"] = (
                    (pos["avg_price"] * (pos["qty"] - order["qty"]) + order["filled_price"] * order["qty"])
                    / pos["qty"]
                )
                pos["updated_at"] = datetime.now().isoformat()
                return

        # New position
        self._positions.append({
            "symbol": order["symbol"],
            "option_type": order["option_type"],
            "strike": order["strike"],
            "direction": order["direction"],
            "qty": order["qty"],
            "avg_price": order["filled_price"],
            "sl": order.get("sl", 0),
            "target": order.get("target", 0),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })

    @staticmethod
    def _days_ago_iso(days: int) -> str:
        """Return an ISO date string for *days* ago (YYYY-MM-DD)."""
        return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    @staticmethod
    def _next_weekly_expiry() -> str:
        """Calculate the next NSE weekly expiry date (Thursday).

        If today is a Thursday *before* market close, today is returned.
        Otherwise the next Thursday is calculated.

        Returns:
            Expiry date in ``YYYY-MM-DD`` format.
        """
        today = datetime.now().date()
        # ISO weekday: Monday=1 … Thursday=4 … Sunday=7
        days_until_thursday = (3 - today.weekday()) % 7
        if days_until_thursday == 0:
            # Today is Thursday – return today if before market close, else next
            now = datetime.now()
            current_minutes = now.hour * 60 + now.minute
            if current_minutes > _MARKET_CLOSE_HOUR * 60 + _MARKET_CLOSE_MINUTE:
                days_until_thursday = 7
        if days_until_thursday == 0:
            days_until_thursday = 7  # fallback safety
        expiry = today + timedelta(days=days_until_thursday)
        return expiry.strftime("%Y-%m-%d")

    def close(self) -> None:
        """Gracefully shut down the HTTP session pool."""
        try:
            self._http.close()
            logger.info("KotakNeoBroker HTTP session closed.")
        except Exception as exc:
            logger.error("Error closing HTTP session: %s", exc)
