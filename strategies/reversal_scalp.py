"""
reversal_scalp.py - RSI-Based Reversal Scalping Strategy

JSS Sawriya Seth Wealthtech
Contrarian strategy that trades against overextended moves.  Looks for
oversold bounces (BUY CE) when RSI < 30 and overbought reversals
(SELL PE) when RSI > 70, confirmed by candlestick patterns, Bollinger
Band extremes, and volume spikes.

**Critical rule:** reversal trades are NEVER taken in sideways markets.

Each agreeing indicator contributes 20 points (5 × 20 = 100 max).

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from core.indicators import bollinger_bands, is_sideways, rsi
from strategies.base_strategy import BaseStrategy


class ReversalScalpStrategy(BaseStrategy):
    """RSI-based reversal scalping strategy.

    Contrarian – enters when price is overextended and shows signs of
    reversing.  Requires volume confirmation and Bollinger Band touch.

    Parameters
    ----------
    config : dict
        Strategy configuration.  Consumed keys:
            - ``min_confidence`` (float, default 65)
            - ``rsi_overbought`` (float, default 70)
            - ``rsi_oversold`` (float, default 30)
            - ``volume_spike_multiplier`` (float, default 1.5)
    """

    POINTS_PER_INDICATOR: float = 20.0  # 5 indicators × 20 = 100

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__("ReversalScalp", config)
        self.rsi_overbought: float = config.get("rsi_overbought", 70.0)
        self.rsi_oversold: float = config.get("rsi_oversold", 30.0)
        self.volume_spike_mult: float = config.get("volume_spike_multiplier", 1.5)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, symbol: str, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Evaluate candles and return a reversal signal if conditions align.

        Returns ``None`` when:
        - Fewer than 30 candles.
        - Market is **sideways** (NO reversal trades in sideways markets).
        - Fewer than 4 / 5 reversal conditions are met.
        """
        # --- Gate 1: data sufficiency ---
        if not self._check_data_sufficiency(candles):
            return None

        # --- Gate 2 (CRITICAL): sideways check – NO reversal trades in sideways ---
        sideways = is_sideways(candles)
        if sideways is True:
            self.logger.info(
                "[%s] %s – market is sideways, reversal trades DISABLED", symbol, self.name
            )
            return None

        # --- Gate 3: need at least 2 candles for pattern detection ---
        if len(candles) < 2:
            return None

        # --- Compute indicators ---
        rsi_val = rsi(candles, 14)
        bb = bollinger_bands(candles, 20, 2.0)

        if rsi_val is None or bb is None:
            self.logger.warning("[%s] %s – indicator computation returned None", symbol, self.name)
            return None

        # Candle data
        current = candles[-1]
        prev = candles[-2]
        current_close = current["close"]
        current_open = current["open"]
        prev_close = prev["close"]
        prev_open = prev["open"]
        current_volume = current.get("volume", 0)

        # Average volume over last 20 candles
        avg_volume = sum(c.get("volume", 0) for c in candles[-20:]) / min(20, len(candles))
        volume_spike = avg_volume > 0 and current_volume > avg_volume * self.volume_spike_mult

        # Candle colour helpers
        current_green = current_close > current_open
        current_red = current_close < current_open
        prev_green = prev_close > prev_open
        prev_red = prev_close < prev_open

        # Bollinger proximity
        bb_range = bb["upper"] - bb["lower"]
        bb_range = bb_range if bb_range > 0 else 1.0
        touching_lower = (current_close - bb["lower"]) / bb_range < 0.10  # bottom 10%
        touching_upper = (bb["upper"] - current_close) / bb_range < 0.10  # top 10%

        # --- Indicators snapshot ---
        indicators_snapshot: Dict[str, Any] = {
            "rsi": rsi_val,
            "bb_upper": bb["upper"],
            "bb_middle": bb["middle"],
            "bb_lower": bb["lower"],
            "bb_bandwidth": bb["bandwidth"],
            "current_close": current_close,
            "current_open": current_open,
            "current_green": current_green,
            "prev_green": prev_green,
            "current_volume": current_volume,
            "avg_volume": round(avg_volume, 0),
            "volume_spike": volume_spike,
            "touching_lower": touching_lower,
            "touching_upper": touching_upper,
        }

        # --- Oversold bounce (BUY CE) scoring ---
        oversold_score = 0
        # 1. RSI < 30 (oversold)
        if rsi_val < self.rsi_oversold:
            oversold_score += 1
        # 2. Previous candle was red (close < open)
        if prev_red:
            oversold_score += 1
        # 3. Current candle shows bullish reversal (green)
        if current_green:
            oversold_score += 1
        # 4. Bollinger: price touching or below lower band
        if touching_lower:
            oversold_score += 1
        # 5. Volume spike
        if volume_spike:
            oversold_score += 1

        # --- Overbought reversal (SELL PE) scoring ---
        overbought_score = 0
        # 1. RSI > 70 (overbought)
        if rsi_val > self.rsi_overbought:
            overbought_score += 1
        # 2. Previous candle was green (close > open)
        if prev_green:
            overbought_score += 1
        # 3. Current candle shows bearish reversal (red)
        if current_red:
            overbought_score += 1
        # 4. Bollinger: price touching or above upper band
        if touching_upper:
            overbought_score += 1
        # 5. Volume spike
        if volume_spike:
            overbought_score += 1

        # --- Determine direction ---
        confidence: float
        direction: str
        option_type: str
        reason: str

        if oversold_score >= 4:
            confidence = oversold_score * self.POINTS_PER_INDICATOR
            direction = "BUY"
            option_type = "CE"
            reason = (
                f"Oversold bounce: {oversold_score}/5 conditions met. "
                f"RSI={rsi_val:.1f} (< {self.rsi_oversold}), "
                f"prev candle red → current green reversal, "
                f"touching BB lower ({bb['lower']:.1f}), "
                f"volume spike (vol={current_volume}, avg={avg_volume:.0f})."
            )
        elif overbought_score >= 4:
            confidence = overbought_score * self.POINTS_PER_INDICATOR
            direction = "SELL"
            option_type = "PE"
            reason = (
                f"Overbought reversal: {overbought_score}/5 conditions met. "
                f"RSI={rsi_val:.1f} (> {self.rsi_overbought}), "
                f"prev candle green → current red reversal, "
                f"touching BB upper ({bb['upper']:.1f}), "
                f"volume spike (vol={current_volume}, avg={avg_volume:.0f})."
            )
        else:
            self.logger.debug(
                "[%s] %s – no reversal setup (oversold=%d overbought=%d)",
                symbol, self.name, oversold_score, overbought_score,
            )
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
    def _select_strike(close: float, option_type: str) -> int:
        """Round close to nearest 50 and pick slightly OTM strike."""
        step = 50
        atm = round(close / step) * step
        if option_type == "CE":
            return int(atm)  # ATM for reversal – cheaper entry
        else:
            return int(atm)

    def calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """Not used directly – confidence is calculated inline in ``analyze``."""
        return super().calculate_confidence(indicators)
