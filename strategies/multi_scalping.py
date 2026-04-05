"""
multi_scalping.py - Multi-Indicator Scalping Strategy

JSS Sawriya Seth Wealthtech
Fast entries / exits for quick profits using triple-EMA alignment,
Bollinger Band bounces, RSI mid-line crosses, and ATR volatility
filtering.

Designed for 1-2 minute timeframes.  Very tight SL (1 %) and quick
target (1.5 %).

Each agreeing indicator contributes 15 points toward confidence
(4 × 15 = 60 max from indicators).  An additional **volatility
bonus** of up to 20 points is awarded when ATR is well above the
minimum threshold, bringing the theoretical max to ~80.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.indicators import atr, bollinger_bands, ema, is_sideways, rsi
from strategies.base_strategy import BaseStrategy


class MultiScalpingStrategy(BaseStrategy):
    """Multi-indicator scalping strategy.

    Enters on triple-EMA alignment + Bollinger Band bounce + RSI cross +
    sufficient volatility.  Exits quickly with tight SL / target.

    Parameters
    ----------
    config : dict
        Strategy configuration.  Consumed keys:
            - ``min_confidence`` (float, default 65)
            - ``atr_min`` (float, default 20) – minimum ATR to trade.
            - ``sl_pct`` (float, default 1.0) – stop-loss as % of entry.
            - ``target_pct`` (float, default 1.5) – target as % of entry.
    """

    POINTS_PER_INDICATOR: float = 15.0
    MAX_VOLATILITY_BONUS: float = 20.0

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__("MultiScalping", config)
        self.atr_min: float = config.get("atr_min", 20.0)
        self.sl_pct: float = config.get("sl_pct", 1.0)
        self.target_pct: float = config.get("target_pct", 1.5)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, symbol: str, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Evaluate candles and return a signal if scalping conditions align.

        Returns ``None`` when:
        - Fewer than 30 candles.
        - Market is sideways.
        - Fewer than 4 / 4 core indicators agree (after volatility bonus,
          confidence still < min_confidence).
        """
        # --- Gate 1: data sufficiency ---
        if not self._check_data_sufficiency(candles):
            return None

        # --- Gate 2: sideways check ---
        sideways = is_sideways(candles)
        if sideways is True:
            self.logger.info("[%s] %s – market is sideways, skipping", symbol, self.name)
            return None

        # --- Compute indicators ---
        ema5 = ema(candles, 5)
        ema13 = ema(candles, 13)
        ema26 = ema(candles, 26)
        rsi_val = rsi(candles, 14)
        bb = bollinger_bands(candles, 20, 2.0)
        atr_val = atr(candles, 14)

        if any(v is None for v in [ema5, ema13, ema26, rsi_val, bb, atr_val]):
            self.logger.warning("[%s] %s – indicator computation returned None", symbol, self.name)
            return None

        ema5_latest = self._latest_valid(ema5)
        ema13_latest = self._latest_valid(ema13)
        ema26_latest = self._latest_valid(ema26)
        current_close = candles[-1]["close"]
        prev_close = candles[-2]["close"] if len(candles) >= 2 else current_close

        # --- Gate 3: volatility check ---
        if atr_val < self.atr_min:
            self.logger.info(
                "[%s] %s – ATR %.2f below minimum %.2f, skipping",
                symbol, self.name, atr_val, self.atr_min,
            )
            return None

        # --- Scoring ---
        indicators_snapshot: Dict[str, Any] = {
            "ema5": round(ema5_latest, 2),
            "ema13": round(ema13_latest, 2),
            "ema26": round(ema26_latest, 2),
            "rsi": rsi_val,
            "bb_upper": bb["upper"],
            "bb_middle": bb["middle"],
            "bb_lower": bb["lower"],
            "bb_bandwidth": bb["bandwidth"],
            "atr": atr_val,
            "close": current_close,
            "prev_close": prev_close,
            "sl_pct": self.sl_pct,
            "target_pct": self.target_pct,
        }

        # Bollinger proximity helpers
        bb_range = bb["upper"] - bb["lower"]
        bb_range = bb_range if bb_range > 0 else 1.0
        near_lower = (current_close - bb["lower"]) / bb_range < 0.25  # bottom 25%
        near_upper = (bb["upper"] - current_close) / bb_range < 0.25  # top 25%

        # RSI crossing 50 from below = RSI > 50 but previous implied RSI < 50
        # We use current RSI > 50 and current close > prev close as proxy
        rsi_bullish_cross = rsi_val > 50 and current_close > prev_close
        rsi_bearish_cross = rsi_val < 50 and current_close < prev_close

        # --- Bullish (BUY CE) scoring ---
        bullish_score = 0
        # 1. Triple EMA alignment: EMA 5 > EMA 13 > EMA 26
        if ema5_latest > ema13_latest > ema26_latest:
            bullish_score += 1
        # 2. Bollinger: price near lower band and bouncing up
        if near_lower and current_close > prev_close:
            bullish_score += 1
        # 3. RSI crossing above 50
        if rsi_bullish_cross:
            bullish_score += 1
        # 4. ATR shows adequate volatility (already checked, but count it)
        if atr_val >= self.atr_min:
            bullish_score += 1

        # --- Bearish (SELL PE) scoring ---
        bearish_score = 0
        # 1. Triple EMA alignment: EMA 5 < EMA 13 < EMA 26
        if ema5_latest < ema13_latest < ema26_latest:
            bearish_score += 1
        # 2. Bollinger: price near upper band and reversing
        if near_upper and current_close < prev_close:
            bearish_score += 1
        # 3. RSI crossing below 50
        if rsi_bearish_cross:
            bearish_score += 1
        # 4. ATR shows adequate volatility
        if atr_val >= self.atr_min:
            bearish_score += 1

        # Determine direction
        confidence: float
        direction: str
        option_type: str
        reason: str

        if bullish_score >= bearish_score and bullish_score >= 3:
            base_conf = bullish_score * self.POINTS_PER_INDICATOR
            vol_bonus = min((atr_val - self.atr_min) / self.atr_min, 1.0) * self.MAX_VOLATILITY_BONUS
            confidence = base_conf + vol_bonus
            direction = "BUY"
            option_type = "CE"
            reason = (
                f"Bullish scalping: {bullish_score}/4 indicators agree. "
                f"EMA5={ema5_latest:.1f} > EMA13={ema13_latest:.1f} > EMA26={ema26_latest:.1f}, "
                f"RSI={rsi_val:.1f}, ATR={atr_val:.1f}. "
                f"Near BB lower band. SL={self.sl_pct}%, Target={self.target_pct}%."
            )
        elif bearish_score >= 3:
            base_conf = bearish_score * self.POINTS_PER_INDICATOR
            vol_bonus = min((atr_val - self.atr_min) / self.atr_min, 1.0) * self.MAX_VOLATILITY_BONUS
            confidence = base_conf + vol_bonus
            direction = "SELL"
            option_type = "PE"
            reason = (
                f"Bearish scalping: {bearish_score}/4 indicators agree. "
                f"EMA5={ema5_latest:.1f} < EMA13={ema13_latest:.1f} < EMA26={ema26_latest:.1f}, "
                f"RSI={rsi_val:.1f}, ATR={atr_val:.1f}. "
                f"Near BB upper band. SL={self.sl_pct}%, Target={self.target_pct}%."
            )
        else:
            self.logger.debug("[%s] %s – no scalping alignment (bull=%d bear=%d)", symbol, self.name, bullish_score, bearish_score)
            return None

        # --- Gate 4: confidence threshold ---
        if confidence < self.min_confidence:
            self.logger.info(
                "[%s] %s – confidence %.1f below threshold %.1f, skipping",
                symbol, self.name, confidence, self.min_confidence,
            )
            return None

        strike = self._select_strike(current_close, option_type)

        signal = self._build_signal(
            symbol=symbol,
            direction=direction,
            option_type=option_type,
            strike=strike,
            confidence=confidence,
            reason=reason,
            indicators=indicators_snapshot,
        )

        self.logger.info(
            "[%s] %s signal: %s %s @ strike %d (confidence=%.1f)",
            symbol, self.name, direction, option_type, strike, confidence,
        )
        return signal

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _latest_valid(values: List[float]) -> float:
        """Return the most recent non-NaN value from an EMA list."""
        for v in reversed(values):
            if not math.isnan(v):
                return v
        raise ValueError("No valid (non-NaN) values in list")

    @staticmethod
    def _select_strike(close: float, option_type: str) -> int:
        """Round close to the nearest 50 for ATM strike."""
        step = 50
        atm = round(close / step) * step
        if option_type == "CE":
            return int(atm + step)
        else:
            return int(atm - step)

    def calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """Not used directly – confidence is calculated inline in ``analyze``."""
        return super().calculate_confidence(indicators)
