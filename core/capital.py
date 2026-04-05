"""
capital.py - Capital Management Module

JSS Sawriya Seth Wealthtech
Manages trading capital with strict risk controls including a hard floor
of ₹100 (capital must NEVER go below this value), daily loss limits,
max open trades, and dynamic lot sizing based on account growth.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Hard floor – capital must NEVER go below this value
HARD_FLOOR: float = 100.0

# Default configuration
_DEFAULT_CONFIG: dict[str, Any] = {
    "initial_capital": 1000.0,
    "max_daily_loss_percent": 5.0,       # max 5% of initial as daily loss
    "max_open_trades": 3,
    "scale_capital_threshold": 10000.0,   # above this → scale lots
    "lot_multiplier": 50,                 # NIFTY default
}


class CapitalManager:
    """Trading capital manager with safety guardrails.

    The manager persists capital state to the database and enforces:
    - Daily loss cap (percentage of initial capital)
    - Maximum concurrent open trades
    - Hard floor at ₹100 (trade rejected if it would breach)
    - Dynamic lot sizing (1 lot until scaling threshold)

    Args:
        db:    :class:`Database` instance for persistence.
        config: Trading config dict.  Expected keys listed above.
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, db: Any, config: Optional[dict[str, Any]] = None) -> None:
        self._db = db
        self._config = {**_DEFAULT_CONFIG, **(config or {})}
        self._state: Optional[dict[str, Any]] = None
        self._open_trades_count: int = 0

        logger.info(
            "CapitalManager initialised (initial=%.2f, max_daily_loss=%.1f%%, max_open=%d)",
            self._config["initial_capital"],
            self._config["max_daily_loss_percent"],
            self._config["max_open_trades"],
        )

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def load_state(self) -> dict[str, Any]:
        """Load capital state from the database.

        If no row exists, a new record is created with the configured
        ``initial_capital``.

        Returns:
            Current capital state dict.
        """
        state = self._db.get_capital_state()

        if state is None:
            # First time – bootstrap
            initial = self._config["initial_capital"]
            self._db.update_capital(initial, pnl=0.0)
            self._db.reset_daily_counters()
            state = self._db.get_capital_state()

        if state is not None:
            self._state = state
            logger.info(
                "Capital state loaded: current=%.2f, peak=%.2f, total_pnl=%.2f",
                state["current"],
                state["peak"],
                state["total_pnl"],
            )
        else:
            # DB fallback
            self._state = {
                "initial": self._config["initial_capital"],
                "current": self._config["initial_capital"],
                "peak": self._config["initial_capital"],
                "total_pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "total_trades": 0,
                "today_pnl": 0.0,
                "today_trades": 0,
                "today_wins": 0,
                "today_losses": 0,
            }
            logger.warning("Could not load from DB; using in-memory default state.")

        # Refresh open trades count
        open_trades = self._db.get_open_trades()
        self._open_trades_count = len(open_trades)

        return self._state

    def get_state(self) -> dict[str, Any]:
        """Return the current capital state dict.

        If state has not been loaded yet, :meth:`load_state` is called
        automatically.

        Returns:
            Capital state dict matching the shared data structure.
        """
        if self._state is None:
            self.load_state()
        return self._state or {}

    def _refresh_open_count(self) -> None:
        """Re-count open trades from the database."""
        open_trades = self._db.get_open_trades()
        self._open_trades_count = len(open_trades)

    # ------------------------------------------------------------------
    # Trade eligibility checks
    # ------------------------------------------------------------------

    def can_trade(self, trade_value: float) -> bool:
        """Check if the current capital allows a trade of *trade_value*.

        A trade is **rejected** if **any** of the following is true:
        1. ``current_capital - trade_value < HARD_FLOOR``
        2. Today's loss already exceeds ``max_daily_loss_percent`` of initial
        3. Number of open trades >= ``max_open_trades``
        4. Current capital < HARD_FLOOR (already at floor)

        Args:
            trade_value: Total cost / margin required for the trade.

        Returns:
            ``True`` if the trade is permitted, ``False`` otherwise.
        """
        state = self.get_state()
        current = float(state.get("current", 0))
        initial = float(state.get("initial", self._config["initial_capital"]))
        today_pnl = float(state.get("today_pnl", 0))

        # 1. Hard floor check
        if current - trade_value < HARD_FLOOR:
            logger.warning(
                "Trade REJECTED (hard floor): current=%.2f - trade=%.2f < %.2f",
                current, trade_value, HARD_FLOOR,
            )
            return False

        # 2. Already at or below floor
        if current <= HARD_FLOOR:
            logger.warning(
                "Trade REJECTED (capital at/below floor): current=%.2f", current
            )
            return False

        # 3. Daily loss limit
        max_daily_loss = initial * self._config["max_daily_loss_percent"] / 100.0
        if today_pnl < 0 and abs(today_pnl) >= max_daily_loss:
            logger.warning(
                "Trade REJECTED (daily loss limit): today_pnl=%.2f, limit=%.2f",
                today_pnl, -max_daily_loss,
            )
            return False

        # 4. Max open trades
        if self._open_trades_count >= self._config["max_open_trades"]:
            logger.warning(
                "Trade REJECTED (max open trades): %d >= %d",
                self._open_trades_count, self._config["max_open_trades"],
            )
            return False

        logger.debug(
            "Trade ALLOWED: value=%.2f, capital=%.2f, today_pnl=%.2f, open=%d",
            trade_value, current, today_pnl, self._open_trades_count,
        )
        return True

    # ------------------------------------------------------------------
    # Lot sizing
    # ------------------------------------------------------------------

    def get_lot_size(self) -> int:
        """Return the recommended lot size.

        Scaling rules:
        - Capital < ``scale_capital_threshold`` → 1 lot
        - Capital >= threshold → ``floor(current / threshold)`` lots
          (minimum 1, capped at 10 for safety)

        Returns:
            Integer lot size (>= 1).
        """
        state = self.get_state()
        current = float(state.get("current", 0))
        threshold = self._config["scale_capital_threshold"]

        if current < threshold:
            lots = 1
        else:
            lots = int(math.floor(current / threshold))

        lots = max(1, min(lots, 10))  # clamp between 1 and 10

        logger.debug("Lot size: %d (capital=%.2f, threshold=%.2f)", lots, current, threshold)
        return lots

    # ------------------------------------------------------------------
    # Trade value calculation
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_trade_value(
        strike: float | int,
        lot_size: int,
        lot_multiplier: int,
    ) -> float:
        """Calculate the notional trade value.

        ``trade_value = strike × lot_size × lot_multiplier``

        Args:
            strike:         Option premium (entry price) per unit.
            lot_size:       Number of lots.
            lot_multiplier: Points per lot (50 for NIFTY, 25 for BANKNIFTY).

        Returns:
            Total trade value (float).
        """
        return float(strike) * lot_size * lot_multiplier

    # ------------------------------------------------------------------
    # Trade lifecycle
    # ------------------------------------------------------------------

    def record_trade_open(self, trade_value: float) -> bool:
        """Reserve capital when a trade is opened.

        Deducts *trade_value* from the current capital but does **not**
        persist to the DB yet (P&L is calculated at close time).
        Instead, this updates the in-memory state.

        Args:
            trade_value: Cost of the new trade.

        Returns:
            ``True`` if successful.
        """
        state = self.get_state()
        new_capital = float(state.get("current", 0)) - trade_value

        # Safety check
        if new_capital < HARD_FLOOR:
            logger.error(
                "record_trade_open would breach floor: %.2f < %.2f",
                new_capital, HARD_FLOOR,
            )
            return False

        self._state["current"] = round(new_capital, 2)
        self._open_trades_count += 1

        logger.info(
            "Trade OPEN: reserved %.2f, new capital=%.2f, open_trades=%d",
            trade_value, new_capital, self._open_trades_count,
        )
        return True

    def record_trade_close(
        self,
        entry_price: float,
        exit_price: float,
        qty: int,
        lot_size: int,
        strike: int,
        lot_multiplier: int,
    ) -> dict[str, Any]:
        """Calculate P&L and update capital when a trade is closed.

        P&L formula (per-lot, per-point):
        - BUY  → ``pnl = (exit_price - entry_price) × qty × lot_multiplier``
        - SELL → ``pnl = (entry_price - exit_price) × qty × lot_multiplier``

        The returned capital is clamped so it never falls below
        ``HARD_FLOOR`` (₹100).

        Args:
            entry_price:    Price at which the trade was entered.
            exit_price:     Price at which the trade was closed.
            qty:            Total quantity (lots × lot_size).
            lot_size:       Number of lots.
            strike:         Strike price of the option.
            lot_multiplier: Points per lot (50 for NIFTY, 25 for BANKNIFTY).

        Returns:
            Dict with ``pnl``, ``new_capital``, ``is_win``, ``details``.
        """
        state = self.get_state()
        current = float(state.get("current", 0))

        # Calculate P&L
        # For options, qty is typically lots * lot_multiplier is already
        # accounted for in the trade_value. Here we compute raw P&L.
        pnl = (exit_price - entry_price) * qty * lot_multiplier
        pnl = round(pnl, 2)

        # Restore reserved capital + P&L
        trade_value = entry_price * qty * lot_multiplier
        new_capital = current + trade_value + pnl

        # Enforce hard floor
        if new_capital < HARD_FLOOR:
            logger.warning(
                "Capital %.2f would breach floor; clamping to %.2f",
                new_capital, HARD_FLOOR,
            )
            new_capital = HARD_FLOOR

        new_capital = round(new_capital, 2)
        is_win = pnl > 0

        # Persist to database
        self._db.update_capital(new_capital, pnl)

        # Update in-memory state
        if self._state is not None:
            self._state["current"] = new_capital
            self._state["peak"] = max(float(self._state.get("peak", 0)), new_capital)
            self._state["total_pnl"] = round(float(self._state.get("total_pnl", 0)) + pnl, 2)
            self._state["total_trades"] = int(self._state.get("total_trades", 0)) + 1
            if is_win:
                self._state["wins"] = int(self._state.get("wins", 0)) + 1
                self._state["today_wins"] = int(self._state.get("today_wins", 0)) + 1
            else:
                self._state["losses"] = int(self._state.get("losses", 0)) + 1
                self._state["today_losses"] = int(self._state.get("today_losses", 0)) + 1
            self._state["today_pnl"] = round(float(self._state.get("today_pnl", 0)) + pnl, 2)
            self._state["today_trades"] = int(self._state.get("today_trades", 0)) + 1

        self._open_trades_count = max(0, self._open_trades_count - 1)

        result = {
            "pnl": pnl,
            "new_capital": new_capital,
            "is_win": is_win,
            "trade_value": round(trade_value, 2),
            "details": {
                "entry_price": entry_price,
                "exit_price": exit_price,
                "qty": qty,
                "lot_size": lot_size,
                "strike": strike,
                "lot_multiplier": lot_multiplier,
            },
        }

        logger.info(
            "Trade CLOSE: PnL=%.2f (%s), capital=%.2f, peak=%.2f",
            pnl, "WIN" if is_win else "LOSS", new_capital,
            self._state["peak"] if self._state else new_capital,
        )
        return result

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def get_daily_summary(self) -> dict[str, Any]:
        """Get today's trading summary.

        Returns:
            Dict with ``today_pnl``, ``today_trades``, ``today_wins``,
            ``today_losses``, ``today_win_rate``.
        """
        state = self.get_state()
        today_trades = int(state.get("today_trades", 0))
        today_wins = int(state.get("today_wins", 0))

        return {
            "today_pnl": round(float(state.get("today_pnl", 0)), 2),
            "today_trades": today_trades,
            "today_wins": today_wins,
            "today_losses": int(state.get("today_losses", 0)),
            "today_win_rate": round(today_wins / today_trades * 100, 2) if today_trades > 0 else 0.0,
            "current_capital": round(float(state.get("current", 0)), 2),
            "open_trades": self._open_trades_count,
        }

    def get_total_summary(self) -> dict[str, Any]:
        """Get total lifetime trading summary.

        Returns:
            Dict with ``initial``, ``current``, ``peak``, ``total_pnl``,
            ``total_trades``, ``wins``, ``losses``, ``win_rate``,
            ``pnl_percent``.
        """
        state = self.get_state()
        initial = float(state.get("initial", self._config["initial_capital"]))
        current = float(state.get("current", 0))
        total = int(state.get("total_trades", 0))
        wins = int(state.get("wins", 0))

        return {
            "initial": round(initial, 2),
            "current": round(current, 2),
            "peak": round(float(state.get("peak", 0)), 2),
            "total_pnl": round(float(state.get("total_pnl", 0)), 2),
            "total_trades": total,
            "wins": wins,
            "losses": int(state.get("losses", 0)),
            "win_rate": round(wins / total * 100, 2) if total > 0 else 0.0,
            "pnl_percent": round((current - initial) / initial * 100, 2) if initial > 0 else 0.0,
            "today_pnl": round(float(state.get("today_pnl", 0)), 2),
        }

    # ------------------------------------------------------------------
    # Reset / admin
    # ------------------------------------------------------------------

    def reset_to_initial(self) -> bool:
        """Reset capital back to the initial value (for testing).

        Returns:
            ``True`` on success.
        """
        initial = self._config["initial_capital"]
        success = self._db.update_capital(initial, pnl=0.0)
        if success:
            self._db.reset_daily_counters()
            self._state = {
                "initial": initial,
                "current": initial,
                "peak": initial,
                "total_pnl": 0.0,
                "wins": 0,
                "losses": 0,
                "total_trades": 0,
                "today_pnl": 0.0,
                "today_trades": 0,
                "today_wins": 0,
                "today_losses": 0,
            }
            self._open_trades_count = 0
            logger.info("Capital RESET to initial: %.2f", initial)

        return success
