"""
momentum_follow.py - Momentum Following Strategy

JSS Sawriya Seth Wealthtech
Rides strong directional moves by confirming alignment across six
independent technical indicators: EMA crossover, RSI, MACD histogram,
SuperTrend, ADX trend-strength, and VWAP position.

BUY CE  – bullish momentum alignment.
SELL PE – bearish momentum alignment.

Each agreeing indicator contributes ~16.6 points toward a maximum
confidence of 100.  Trades are only taken when confidence >= 65.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.indicators import (
    adx,
    ema,
    get_trend,
    is_sideways,
    macd,
    rsi,
    supertrend,
    vwap,
)
from strategies.base_strategy import BaseStrategy


class MomentumFollowStrategy(BaseStrategy):
    """Momentum following strategy.

    Confirms trend direction with six indicators.  Each indicator that
    agrees with the hypothesised direction adds approximately 16.6
    points to the confidence score (6 × 16.6 ≈ 100).

    Parameters
    ----------
    config : dict
        Strategy configuration.  Consumed keys:
            - ``min_confidence`` (float, default 65)
            - ``adx_threshold`` (float, default 25)
            - ``rsi_overbought`` (float, default 80)
            - ``rsi_oversold`` (float, default 20)
    """

    POINTS_PER_INDICATOR: float = 100.0 / 6.0  # ≈ 16.67

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__("MomentumFollow", config)
        self.adx_threshold: float = config.get("adx_threshold", 25.0)
        self.rsi_overbought: float = config.get("rsi_overbought", 80.0)
        self.rsi_oversold: float = config.get("rsi_oversold", 20.0)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, symbol: str, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Evaluate candles and return a signal if momentum conditions align.

        Returns ``None`` when:
        - Fewer than 30 candles are provided.
        - The market is sideways.
        - Trend is ``NEUTRAL``.
        - Fewer than 4 of 6 indicators agree (confidence < ~66).
        """
        # --- Gate 1: data sufficiency ---
        if not self._check_data_sufficiency(candles):
            return None

        # --- Gate 2: sideways check ---
        sideways = is_sideways(candles)
        if sideways is True:
            self.logger.info("[%s] %s – market is sideways, skipping", symbol, self.name)
            return None

        # --- Gate 3: trend check ---
        trend = get_trend(candles)
        if trend is None or trend == "NEUTRAL":
            self.logger.info("[%s] %s – no clear trend, skipping", symbol, self.name)
            return None

        # --- Compute indicators ---
        ema9 = ema(candles, 9)
        ema21 = ema(candles, 21)
        rsi_val = rsi(candles, 14)
        macd_val = macd(candles)
        st = supertrend(candles, 10, 3.0)
        adx_val = adx(candles, 14)
        vwap_val = vwap(candles)

        # Validate all indicators computed successfully
        if any(v is None for v in [ema9, ema21, rsi_val, macd_val, st, adx_val, vwap_val]):
            self.logger.warning("[%s] %s – indicator computation returned None", symbol, self.name)
            return None

        # Extract latest valid EMA values
        ema9_latest = self._latest_valid(ema9)
        ema21_latest = self._latest_valid(ema21)
        st_latest = st[-1]  # type: ignore[index]

        current_close = candles[-1]["close"]

        # --- Scoring ---
        indicators_snapshot: Dict[str, Any] = {
            "ema9": round(ema9_latest, 2),
            "ema21": round(ema21_latest, 2),
            "rsi": rsi_val,
            "macd_histogram": macd_val["histogram"],
            "macd_line": macd_val["macd_line"],
            "signal_line": macd_val["signal_line"],
            "supertrend_direction": st_latest["direction"],
            "supertrend_value": st_latest["value"],
            "adx": adx_val,
            "vwap": vwap_val,
            "trend": trend,
            "close": current_close,
        }

        # Determine if bullish or bearish conditions are met
        is_bullish = self._check_bullish(
            ema9_latest=ema9_latest,
            ema21_latest=ema21_latest,
            rsi_val=rsi_val,
            macd_histogram=macd_val["histogram"],
            macd_line=macd_val["macd_line"],
            signal_line=macd_val["signal_line"],
            st_direction=st_latest["direction"],
            adx_val=adx_val,
            vwap_val=vwap_val,
            close=current_close,
        )

        is_bearish = self._check_bearish(
            ema9_latest=ema9_latest,
            ema21_latest=ema21_latest,
            rsi_val=rsi_val,
            macd_histogram=macd_val["histogram"],
            macd_line=macd_val["macd_line"],
            signal_line=macd_val["signal_line"],
            st_direction=st_latest["direction"],
            adx_val=adx_val,
            vwap_val=vwap_val,
            close=current_close,
        )

        confidence: float
        direction: str
        option_type: str
        reason: str

        if is_bullish:
            confidence = is_bullish * self.POINTS_PER_INDICATOR
            direction = "BUY"
            option_type = "CE"
            reason = self._build_reason("bullish", is_bullish, indicators_snapshot)
        elif is_bearish:
            confidence = is_bearish * self.POINTS_PER_INDICATOR
            direction = "SELL"
            option_type = "PE"
            reason = self._build_reason("bearish", is_bearish, indicators_snapshot)
        else:
            self.logger.debug("[%s] %s – no momentum alignment found", symbol, self.name)
            return None

        # --- Gate 4: confidence threshold ---
        if confidence < self.min_confidence:
            self.logger.info(
                "[%s] %s – confidence %.1f below threshold %.1f, skipping",
                symbol, self.name, confidence, self.min_confidence,
            )
            return None

        # Choose strike – round current close to nearest 50 (NIFTY-style)
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

    def _check_bullish(
        self,
        ema9_latest: float,
        ema21_latest: float,
        rsi_val: float,
        macd_histogram: float,
        macd_line: float,
        signal_line: float,
        st_direction: str,
        adx_val: float,
        vwap_val: float,
        close: float,
    ) -> int:
        """Count how many bullish conditions are satisfied (0 – 6)."""
        score = 0

        # 1. EMA 9 > EMA 21
        if ema9_latest > ema21_latest:
            score += 1

        # 2. RSI > 55 and < 80
        if 55 < rsi_val < 80:
            score += 1

        # 3. MACD histogram positive AND increasing (macd_line > signal_line)
        if macd_histogram > 0 and macd_line > signal_line:
            score += 1

        # 4. SuperTrend direction UP
        if st_direction == "UP":
            score += 1

        # 5. ADX > 25 (strong trend)
        if adx_val > self.adx_threshold:
            score += 1

        # 6. Price above VWAP
        if close > vwap_val:
            score += 1

        return score

    def _check_bearish(
        self,
        ema9_latest: float,
        ema21_latest: float,
        rsi_val: float,
        macd_histogram: float,
        macd_line: float,
        signal_line: float,
        st_direction: str,
        adx_val: float,
        vwap_val: float,
        close: float,
    ) -> int:
        """Count how many bearish conditions are satisfied (0 – 6)."""
        score = 0

        # 1. EMA 9 < EMA 21
        if ema9_latest < ema21_latest:
            score += 1

        # 2. RSI < 45 and > 20
        if self.rsi_oversold < rsi_val < 45:
            score += 1

        # 3. MACD histogram negative AND decreasing (macd_line < signal_line)
        if macd_histogram < 0 and macd_line < signal_line:
            score += 1

        # 4. SuperTrend direction DOWN
        if st_direction == "DOWN":
            score += 1

        # 5. ADX > 25 (strong trend)
        if adx_val > self.adx_threshold:
            score += 1

        # 6. Price below VWAP
        if close < vwap_val:
            score += 1

        return score

    def _build_reason(
        self,
        direction: str,
        agree_count: int,
        indicators: Dict[str, Any],
    ) -> str:
        """Build a human-readable reason string for the signal."""
        parts: list[str] = [
            f"{direction.upper()} momentum: {agree_count}/6 indicators agree.",
        ]
        if direction == "bullish":
            parts.append(
                f"EMA9={indicators['ema9']} > EMA21={indicators['ema21']}, "
                f"RSI={indicators['rsi']:.1f}, MACD_hist={indicators['macd_histogram']:.2f}, "
                f"ST={indicators['supertrend_direction']}, ADX={indicators['adx']:.1f}, "
                f"VWAP={indicators['vwap']:.2f}"
            )
        else:
            parts.append(
                f"EMA9={indicators['ema9']} < EMA21={indicators['ema21']}, "
                f"RSI={indicators['rsi']:.1f}, MACD_hist={indicators['macd_histogram']:.2f}, "
                f"ST={indicators['supertrend_direction']}, ADX={indicators['adx']:.1f}, "
                f"VWAP={indicators['vwap']:.2f}"
            )
        return " ".join(parts)

    @staticmethod
    def _latest_valid(values: List[float]) -> float:
        """Return the most recent non-NaN value from an EMA list."""
        for v in reversed(values):
            if not math.isnan(v):
                return v
        raise ValueError("No valid (non-NaN) values in list")

    @staticmethod
    def _select_strike(close: float, option_type: str) -> int:
        """Round close to the nearest 50 and adjust for ATM.

        For a BUY CE we round *up* slightly; for SELL PE we round *down*
        slightly so the strike is slightly OTM.
        """
        step = 50
        atm = round(close / step) * step
        if option_type == "CE":
            return int(atm + step)  # 1 strike OTM
        else:
            return int(atm - step)  # 1 strike OTM

    def calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """Not used directly – confidence is calculated inline in ``analyze``."""
        return super().calculate_confidence(indicators)
