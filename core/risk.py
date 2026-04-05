"""
risk.py - Risk Management Module

JSS Sawriya Seth Wealthtech
Enforces stop-loss, target, trailing-stop, time-based exits,
daily loss limits, and strategy cooldowns.  Every trade signal
must pass through :meth:`check_risk` before execution.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Square-off time (all open positions must be closed by this time)
_SQUARE_OFF_TIME: time = time(15, 15)

# Default configuration
_DEFAULT_CONFIG: dict[str, Any] = {
    "sl_percent": 15.0,            # Stop-loss % from entry
    "risk_reward_ratio": 2.0,      # Minimum risk:reward ratio
    "trailing_sl_activation_pct": 3.0,  # Trailing SL activates when price moves this % in favour
    "trailing_sl_trail_pct": 1.5,       # Trail by this % from highest favourable
    "max_daily_loss_percent": 5.0,      # Max daily loss as % of initial capital
    "strategy_cooldown_minutes": 15,    # Cooldown after a strategy loss
    "max_consecutive_losses": 3,        # Pause trading after N consecutive losses
}


class RiskManager:
    """Comprehensive risk manager for options trading.

    Provides stop-loss / target calculation, trailing-stop logic,
    time-based square-off checks, daily loss limits, and per-strategy
    cooldown tracking.

    Args:
        config:         Trading config dict.
        capital_manager: :class:`CapitalManager` instance (for capital queries).
    """

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        capital_manager: Any = None,
    ) -> None:
        self._config = {**_DEFAULT_CONFIG, **(config or {})}
        self._capital_manager = capital_manager

        # Strategy cooldowns: {strategy_name: cooldown_until_datetime}
        self._cooldowns: dict[str, datetime] = {}
        self._lock = threading.Lock()

        # Consecutive loss tracking
        self._consecutive_losses: int = 0

        logger.info(
            "RiskManager initialised (sl=%.1f%%, rr=%.1f, trail_act=%.1f%%, trail=%.1f%%)",
            self._config["sl_percent"],
            self._config["risk_reward_ratio"],
            self._config["trailing_sl_activation_pct"],
            self._config["trailing_sl_trail_pct"],
        )

    # ------------------------------------------------------------------
    # Stop-loss & Target
    # ------------------------------------------------------------------

    def calculate_sl(self, entry_price: float, direction: str) -> float:
        """Calculate the stop-loss price for a trade.

        - BUY:  ``entry_price × (1 - sl_percent / 100)``
        - SELL: ``entry_price × (1 + sl_percent / 100)``

        Args:
            entry_price: Trade entry price.
            direction:   ``"BUY"`` or ``"SELL"``.

        Returns:
            Stop-loss price (float).
        """
        sl_pct = self._config["sl_percent"]
        direction = direction.upper()

        if direction == "BUY":
            sl = entry_price * (1 - sl_pct / 100)
        elif direction == "SELL":
            sl = entry_price * (1 + sl_pct / 100)
        else:
            logger.warning("Unknown direction '%s'; defaulting to BUY SL.", direction)
            sl = entry_price * (1 - sl_pct / 100)

        sl = round(sl, 2)
        logger.debug("SL calculated: entry=%.2f, %s → sl=%.2f", entry_price, direction, sl)
        return sl

    def calculate_target(
        self,
        entry_price: float,
        direction: str,
        risk_reward: float | None = None,
    ) -> float:
        """Calculate the target price using a risk-reward ratio.

        The risk distance (|entry - SL|) is multiplied by *risk_reward*
        to determine the target distance from entry.

        - BUY:  ``entry + (entry - sl) × risk_reward``
        - SELL: ``entry - (sl - entry) × risk_reward``

        Args:
            entry_price:  Trade entry price.
            direction:    ``"BUY"`` or ``"SELL"``.
            risk_reward:  Risk-reward ratio (default from config).

        Returns:
            Target price (float).
        """
        if risk_reward is None:
            risk_reward = self._config["risk_reward_ratio"]

        sl = self.calculate_sl(entry_price, direction)
        risk_distance = abs(entry_price - sl)

        if risk_distance <= 0:
            logger.warning("Risk distance is 0; returning 2x entry as target.")
            return round(entry_price * 2, 2)

        direction = direction.upper()

        if direction == "BUY":
            target = entry_price + (risk_distance * risk_reward)
        else:
            target = entry_price - (risk_distance * risk_reward)

        target = round(target, 2)
        logger.debug(
            "Target calculated: entry=%.2f, %s, rr=%.1f → target=%.2f",
            entry_price, direction, risk_reward, target,
        )
        return target

    # ------------------------------------------------------------------
    # Trailing Stop-Loss
    # ------------------------------------------------------------------

    def calculate_trailing_sl(
        self,
        entry_price: float,
        direction: str,
        current_price: float,
        activation_pct: float | None = None,
        trail_pct: float | None = None,
    ) -> float:
        """Calculate a new trailing SL based on price movement.

        The trailing SL **only activates** once the price has moved at
        least *activation_pct* in the favourable direction from the
        entry.  After activation, it trails by *trail_pct* from the
        highest (BUY) or lowest (SELL) price seen.

        Args:
            entry_price:     Original trade entry price.
            direction:       ``"BUY"`` or ``"SELL"``.
            current_price:   Current market price of the option.
            activation_pct:  % move required to activate (default from config).
            trail_pct:       % to trail from favourable extreme (default from config).

        Returns:
            New trailing SL price (float).  Returns the original SL if
            trailing has not yet activated (caller should use the
            regular SL in that case).
        """
        if activation_pct is None:
            activation_pct = self._config["trailing_sl_activation_pct"]
        if trail_pct is None:
            trail_pct = self._config["trailing_sl_trail_pct"]

        direction = direction.upper()
        activation_threshold = entry_price * (activation_pct / 100)

        if direction == "BUY":
            # Favourable move = price goes UP
            favourable_move = current_price - entry_price
            if favourable_move < activation_threshold:
                # Not yet activated
                return self.calculate_sl(entry_price, direction)

            # Trail from highest price seen
            # The trailing SL = current_price * (1 - trail_pct / 100)
            trailing = current_price * (1 - trail_pct / 100)
            return round(max(trailing, entry_price), 2)  # never below entry

        elif direction == "SELL":
            # Favourable move = price goes DOWN
            favourable_move = entry_price - current_price
            if favourable_move < activation_threshold:
                return self.calculate_sl(entry_price, direction)

            trailing = current_price * (1 + trail_pct / 100)
            return round(min(trailing, entry_price), 2)  # never above entry

        else:
            logger.warning("Unknown direction '%s' for trailing SL.", direction)
            return self.calculate_sl(entry_price, "BUY")

    # ------------------------------------------------------------------
    # Exit checks
    # ------------------------------------------------------------------

    def should_exit_by_sl(
        self, trade: dict[str, Any], current_ltp: float
    ) -> tuple[bool, str]:
        """Check if the current price has hit the stop-loss.

        Args:
            trade:      Trade dict (must have ``sl``, ``direction``).
            current_ltp: Current last traded price.

        Returns:
            Tuple ``(triggered: bool, reason: str)``.
        """
        sl = float(trade.get("sl", 0))
        direction = trade.get("direction", "BUY").upper()

        if sl <= 0:
            return False, ""

        if direction == "BUY" and current_ltp <= sl:
            return True, f"SL HIT: LTP={current_ltp:.2f} <= SL={sl:.2f}"
        elif direction == "SELL" and current_ltp >= sl:
            return True, f"SL HIT: LTP={current_ltp:.2f} >= SL={sl:.2f}"

        return False, ""

    def should_exit_by_target(
        self, trade: dict[str, Any], current_ltp: float
    ) -> tuple[bool, str]:
        """Check if the current price has hit the target.

        Args:
            trade:      Trade dict (must have ``target``, ``direction``).
            current_ltp: Current last traded price.

        Returns:
            Tuple ``(triggered: bool, reason: str)``.
        """
        target = float(trade.get("target", 0))
        direction = trade.get("direction", "BUY").upper()

        if target <= 0:
            return False, ""

        if direction == "BUY" and current_ltp >= target:
            return True, f"TARGET HIT: LTP={current_ltp:.2f} >= Target={target:.2f}"
        elif direction == "SELL" and current_ltp <= target:
            return True, f"TARGET HIT: LTP={current_ltp:.2f} <= Target={target:.2f}"

        return False, ""

    def should_exit_by_trailing(
        self, trade: dict[str, Any], current_ltp: float
    ) -> tuple[bool, str]:
        """Check if the trailing SL has been triggered.

        If ``trailing_sl`` is set on the trade (non-zero), check if
        current price has breached it.  Also updates the trailing SL
        to a tighter value if the price continues to move favourably.

        Args:
            trade:      Trade dict (must have ``trailing_sl``, ``direction``,
                        ``entry_price``).
            current_ltp: Current last traded price.

        Returns:
            Tuple ``(triggered: bool, reason: str)``.
        """
        trailing_sl = float(trade.get("trailing_sl", 0))
        direction = trade.get("direction", "BUY").upper()
        entry_price = float(trade.get("entry_price", 0))

        if trailing_sl <= 0:
            return False, ""

        # Check if trailing is breached
        if direction == "BUY" and current_ltp <= trailing_sl:
            return True, f"TRAILING SL HIT: LTP={current_ltp:.2f} <= Trail={trailing_sl:.2f}"
        elif direction == "SELL" and current_ltp >= trailing_sl:
            return True, f"TRAILING SL HIT: LTP={current_ltp:.2f} >= Trail={trailing_sl:.2f}"

        # Update trailing SL if price moved further favourably
        new_trail = self.calculate_trailing_sl(
            entry_price, direction, current_ltp
        )

        if direction == "BUY":
            # For BUY, trailing SL should only go UP (tighter)
            if new_trail > trailing_sl:
                trade["trailing_sl"] = round(new_trail, 2)
                logger.debug(
                    "Trailing SL updated: %.2f → %.2f", trailing_sl, new_trail
                )
        elif direction == "SELL":
            # For SELL, trailing SL should only go DOWN (tighter)
            if new_trail < trailing_sl:
                trade["trailing_sl"] = round(new_trail, 2)
                logger.debug(
                    "Trailing SL updated: %.2f → %.2f", trailing_sl, new_trail
                )

        return False, ""

    def should_exit_by_time(self, trade: dict[str, Any]) -> tuple[bool, str]:
        """Check if it is past the square-off time (15:15 IST).

        Args:
            trade: Trade dict.

        Returns:
            Tuple ``(should_exit: bool, reason: str)``.
        """
        now = datetime.now().time()
        if now >= _SQUARE_OFF_TIME:
            return True, f"SQUARE-OFF TIME: {now.strftime('%H:%M')} >= {_SQUARE_OFF_TIME.strftime('%H:%M')}"
        return False, ""

    def should_exit_by_max_loss(
        self, capital: dict[str, Any], daily_pnl: float
    ) -> bool:
        """Check if the daily loss has exceeded the configured maximum.

        Args:
            capital:   Capital state dict.
            daily_pnl: Today's cumulative P&L.

        Returns:
            ``True`` if the daily loss limit has been breached.
        """
        initial = float(capital.get("initial", 1000))
        max_loss = initial * self._config["max_daily_loss_percent"] / 100.0

        if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
            logger.warning(
                "Max daily loss BREACHED: today_pnl=%.2f >= limit=%.2f",
                daily_pnl, -max_loss,
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Strategy cooldowns
    # ------------------------------------------------------------------

    def is_cooldown_active(self, strategy_name: str) -> bool:
        """Check if a strategy is in cooldown.

        Args:
            strategy_name: Strategy identifier.

        Returns:
            ``True`` if the strategy is still cooling down.
        """
        with self._lock:
            cooldown_until = self._cooldowns.get(strategy_name)
            if cooldown_until is None:
                return False
            if datetime.now() >= cooldown_until:
                # Cooldown expired; clean up
                del self._cooldowns[strategy_name]
                return False
            remaining = (cooldown_until - datetime.now()).total_seconds()
            logger.debug(
                "Strategy '%s' is in cooldown (%.0fs remaining)",
                strategy_name, remaining,
            )
            return True

    def set_cooldown(self, strategy_name: str, minutes: int | None = None) -> None:
        """Activate a cooldown for a strategy after a losing trade.

        Args:
            strategy_name: Strategy identifier.
            minutes:       Cooldown duration in minutes (default from config).
        """
        if minutes is None:
            minutes = self._config["strategy_cooldown_minutes"]

        with self._lock:
            cooldown_until = datetime.now() + __import__("datetime").timedelta(minutes=minutes)
            self._cooldowns[strategy_name] = cooldown_until

        logger.info(
            "Cooldown set for strategy '%s': %d minutes (until %s)",
            strategy_name, minutes, cooldown_until.strftime("%H:%M:%S"),
        )

    def clear_cooldown(self, strategy_name: str) -> None:
        """Manually clear a strategy's cooldown.

        Args:
            strategy_name: Strategy identifier.
        """
        with self._lock:
            self._cooldowns.pop(strategy_name, None)
        logger.debug("Cooldown cleared for strategy '%s'.", strategy_name)

    # ------------------------------------------------------------------
    # Consecutive loss tracking
    # ------------------------------------------------------------------

    def record_loss(self) -> None:
        """Increment the consecutive loss counter."""
        self._consecutive_losses += 1
        logger.info(
            "Consecutive losses: %d/%d",
            self._consecutive_losses,
            self._config["max_consecutive_losses"],
        )

    def record_win(self) -> None:
        """Reset the consecutive loss counter on a win."""
        self._consecutive_losses = 0

    def is_consecutive_limit_reached(self) -> bool:
        """Check if trading should pause due to consecutive losses.

        Returns:
            ``True`` if consecutive losses >= configured maximum.
        """
        if self._consecutive_losses >= self._config["max_consecutive_losses"]:
            logger.warning(
                "Consecutive loss limit reached: %d >= %d",
                self._consecutive_losses,
                self._config["max_consecutive_losses"],
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Comprehensive risk check
    # ------------------------------------------------------------------

    def check_risk(self, trade_signal: dict[str, Any]) -> dict[str, Any]:
        """Perform a comprehensive pre-trade risk assessment.

        Checks:
        1. Strategy cooldown active → reject
        2. Consecutive loss limit → reject
        3. Daily max loss → reject
        4. Capital floor (₹100) → reject
        5. Max open trades → reject

        If all checks pass, computes SL and target.

        Args:
            trade_signal: Signal dict.  Expected keys: ``direction``,
                          ``option_type``, ``strike``, ``symbol``,
                          ``strategy_name``, ``confidence``,
                          ``entry_price`` (optional).

        Returns:
            Dict with keys:
            - ``allowed``   (bool): Whether the trade is permitted.
            - ``reason``    (str):  Human-readable reason.
            - ``sl``        (float): Stop-loss price.
            - ``target``    (float): Target price.
            - ``position_size`` (int): Recommended position size (lots).
        """

        strategy = trade_signal.get("strategy_name", "UNKNOWN")

        # 1. Strategy cooldown
        if self.is_cooldown_active(strategy):
            return {
                "allowed": False,
                "reason": f"Strategy '{strategy}' is in cooldown after recent loss",
                "sl": 0,
                "target": 0,
                "position_size": 0,
            }

        # 2. Consecutive loss limit
        if self.is_consecutive_limit_reached():
            return {
                "allowed": False,
                "reason": (
                    f"Consecutive loss limit reached ({self._consecutive_losses}/"
                    f"{self._config['max_consecutive_losses']}); trading paused"
                ),
                "sl": 0,
                "target": 0,
                "position_size": 0,
            }

        # 3. Daily max loss (check via capital manager if available)
        if self._capital_manager is not None:
            state = self._capital_manager.get_state()
            daily_pnl = float(state.get("today_pnl", 0))
            initial = float(state.get("initial", 1000))
            max_loss = initial * self._config["max_daily_loss_percent"] / 100.0

            if daily_pnl < 0 and abs(daily_pnl) >= max_loss:
                return {
                    "allowed": False,
                    "reason": (
                        f"Daily loss limit reached: {daily_pnl:.2f} "
                        f"(max allowed: {-max_loss:.2f})"
                    ),
                    "sl": 0,
                    "target": 0,
                    "position_size": 0,
                }

            # 4. Capital floor check
            current = float(state.get("current", 0))
            if current <= 100:
                return {
                    "allowed": False,
                    "reason": f"Capital at floor (₹{current:.2f}); trading halted",
                    "sl": 0,
                    "target": 0,
                    "position_size": 0,
                }

        # 5. Compute SL & target
        entry_price = float(trade_signal.get("entry_price", 0))
        if entry_price <= 0:
            entry_price = float(trade_signal.get("strike", 0))

        direction = trade_signal.get("direction", "BUY").upper()
        sl = self.calculate_sl(entry_price, direction)
        target = self.calculate_target(entry_price, direction)

        # 6. Position sizing (lot size from capital manager)
        position_size = 1
        if self._capital_manager is not None:
            position_size = self._capital_manager.get_lot_size()

        # Trade value check
        lot_multiplier = 50  # default NIFTY
        symbol = trade_signal.get("symbol", "NIFTY").upper()
        if symbol == "BANKNIFTY":
            lot_multiplier = 25

        trade_value = entry_price * position_size * lot_multiplier
        if self._capital_manager is not None and not self._capital_manager.can_trade(trade_value):
            return {
                "allowed": False,
                "reason": (
                    f"Insufficient capital for trade value ₹{trade_value:.2f} "
                    f"(capital: ₹{self._capital_manager.get_state().get('current', 0):.2f})"
                ),
                "sl": sl,
                "target": target,
                "position_size": 0,
            }

        # Confidence gate: reject very low-confidence signals
        confidence = float(trade_signal.get("confidence", 0))
        if confidence < 0.3:
            return {
                "allowed": False,
                "reason": f"Signal confidence too low: {confidence:.2f} (min 0.30)",
                "sl": sl,
                "target": target,
                "position_size": 0,
            }

        logger.info(
            "Risk check PASSED: %s %s %s → SL=%.2f, Target=%.2f, Lots=%d",
            direction, symbol, trade_signal.get("option_type", "?"),
            sl, target, position_size,
        )

        return {
            "allowed": True,
            "reason": "All risk checks passed",
            "sl": sl,
            "target": target,
            "position_size": position_size,
        }
