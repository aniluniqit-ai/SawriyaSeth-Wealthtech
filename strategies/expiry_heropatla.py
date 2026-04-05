"""
expiry_heropatla.py - Expiry Day Special Strategy

JSS Sawriya Seth Wealthtech
Capitalises on the accelerated premium decay (theta) that occurs on
weekly expiry days after 13:00 IST.  Uses cheap OTM options for
leveraged directional bets.

Only activates on **Thursday** (weekly expiry for NIFTY / BANKNIFTY).

5 indicators at 20 points each + 10 bonus for expiry day = max 110
(clamped to 100).  Tight SL (15 % of premium) and quick target
(30–50 %).

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.indicators import adx, ema, get_trend, is_sideways, rsi, supertrend
from strategies.base_strategy import BaseStrategy


class ExpiryHeropatlaStrategy(BaseStrategy):
    """Expiry day special strategy ("Heropatla" = hero play).

    Exploits theta decay acceleration on weekly expiry afternoons by
    buying cheap OTM options when a strong trend is confirmed.

    Parameters
    ----------
    config : dict
        Strategy configuration.  Consumed keys:
            - ``min_confidence`` (float, default 65)
            - ``activation_hour`` (int, default 13) – hour (24h) after
              which the strategy is active.
            - ``adx_threshold`` (float, default 30) – minimum ADX for a
              directional move on expiry.
            - ``rsi_overbought`` (float, default 70)
            - ``sl_pct`` (float, default 15.0) – stop-loss % of premium.
            - ``target_pct`` (float, default 40.0) – target % of premium.
            - ``otm_strikes`` (int, default 2) – number of strikes OTM.
    """

    POINTS_PER_INDICATOR: float = 20.0
    EXPIRY_DAY_BONUS: float = 10.0

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__("ExpiryHeropatla", config)
        self.activation_hour: int = config.get("activation_hour", 13)
        self.adx_threshold: float = config.get("adx_threshold", 30.0)
        self.rsi_overbought: float = config.get("rsi_overbought", 70.0)
        self.sl_pct: float = config.get("sl_pct", 15.0)
        self.target_pct: float = config.get("target_pct", 40.0)
        self.otm_strikes: int = config.get("otm_strikes", 2)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def analyze(self, symbol: str, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Evaluate candles and return a signal if expiry-day conditions align.

        Returns ``None`` when:
        - Fewer than 30 candles.
        - Not an expiry day (not Thursday) or time is before activation hour.
        - Market is sideways.
        - Trend is not clearly directional.
        - Fewer than 3 / 5 core indicators agree (after bonus, confidence
          still < min_confidence).
        """
        # --- Gate 1: data sufficiency ---
        if not self._check_data_sufficiency(candles):
            return None

        # --- Gate 2: expiry day check ---
        now = datetime.now()
        is_expiry_day = self._is_expiry_day(now)

        if not is_expiry_day:
            self.logger.debug("[%s] %s – not an expiry day, skipping", symbol, self.name)
            return None

        # --- Gate 3: time check (after activation hour) ---
        if now.hour < self.activation_hour:
            self.logger.info(
                "[%s] %s – current hour %d, need ≥ %d, skipping",
                symbol, self.name, now.hour, self.activation_hour,
            )
            return None

        # --- Gate 4: sideways check ---
        sideways = is_sideways(candles)
        if sideways is True:
            self.logger.info("[%s] %s – market is sideways on expiry, skipping", symbol, self.name)
            return None

        # --- Gate 5: trend check ---
        trend = get_trend(candles)
        if trend is None or trend == "NEUTRAL":
            self.logger.info("[%s] %s – no clear trend on expiry, skipping", symbol, self.name)
            return None

        # --- Compute indicators ---
        ema9 = ema(candles, 9)
        ema21 = ema(candles, 21)
        rsi_val = rsi(candles, 14)
        st = supertrend(candles, 10, 3.0)
        adx_val = adx(candles, 14)

        if any(v is None for v in [ema9, ema21, rsi_val, st, adx_val]):
            self.logger.warning("[%s] %s – indicator computation returned None", symbol, self.name)
            return None

        ema9_latest = self._latest_valid(ema9)
        ema21_latest = self._latest_valid(ema21)
        st_latest = st[-1]  # type: ignore[index]
        current_close = candles[-1]["close"]

        # --- Scoring ---
        indicators_snapshot: Dict[str, Any] = {
            "ema9": round(ema9_latest, 2),
            "ema21": round(ema21_latest, 2),
            "rsi": rsi_val,
            "supertrend_direction": st_latest["direction"],
            "supertrend_value": st_latest["value"],
            "adx": adx_val,
            "trend": trend,
            "close": current_close,
            "is_expiry_day": True,
            "current_time": now.strftime("%H:%M:%S"),
            "sl_pct": self.sl_pct,
            "target_pct": self.target_pct,
            "otm_strikes": self.otm_strikes,
        }

        # --- Bullish (BUY CE) scoring ---
        bullish_score = 0
        # 1. Expiry day (always true at this point)
        bullish_score += 1
        # 2. Clear bullish trend: EMA 9 > 21
        if ema9_latest > ema21_latest:
            bullish_score += 1
        # 3. SuperTrend UP
        if st_latest["direction"] == "UP":
            bullish_score += 1
        # 4. ADX > 30 (strong directional move)
        if adx_val > self.adx_threshold:
            bullish_score += 1
        # 5. RSI not overbought (< 70)
        if rsi_val < self.rsi_overbought:
            bullish_score += 1

        # --- Bearish (BUY PE) scoring ---
        bearish_score = 0
        # 1. Expiry day
        bearish_score += 1
        # 2. Clear bearish trend: EMA 9 < 21
        if ema9_latest < ema21_latest:
            bearish_score += 1
        # 3. SuperTrend DOWN
        if st_latest["direction"] == "DOWN":
            bearish_score += 1
        # 4. ADX > 30
        if adx_val > self.adx_threshold:
            bearish_score += 1
        # 5. RSI not oversold (> 30) – inverted for bearish: not too oversold
        if rsi_val > 30:
            bearish_score += 1

        # --- Determine direction ---
        confidence: float
        direction: str
        option_type: str
        reason: str

        if bullish_score >= 4 and trend in ("BULL", "STRONG_BULL"):
            confidence = min(
                bullish_score * self.POINTS_PER_INDICATOR + self.EXPIRY_DAY_BONUS,
                100.0,
            )
            direction = "BUY"
            option_type = "CE"
            otm_strike = self._select_otm_strike(current_close, "CE")
            reason = (
                f"Expiry heropatla BULL: {bullish_score}/5 indicators + expiry bonus. "
                f"EMA9={ema9_latest:.1f} > EMA21={ema21_latest:.1f}, "
                f"ST={st_latest['direction']}, ADX={adx_val:.1f}, RSI={rsi_val:.1f}. "
                f"OTM strike {otm_strike} ({self.otm_strikes} strikes OTM). "
                f"SL={self.sl_pct}%, Target={self.target_pct}%."
            )
        elif bearish_score >= 4 and trend in ("BEAR", "STRONG_BEAR"):
            confidence = min(
                bearish_score * self.POINTS_PER_INDICATOR + self.EXPIRY_DAY_BONUS,
                100.0,
            )
            direction = "BUY"
            option_type = "PE"
            otm_strike = self._select_otm_strike(current_close, "PE")
            reason = (
                f"Expiry heropatla BEAR: {bearish_score}/5 indicators + expiry bonus. "
                f"EMA9={ema9_latest:.1f} < EMA21={ema21_latest:.1f}, "
                f"ST={st_latest['direction']}, ADX={adx_val:.1f}, RSI={rsi_val:.1f}. "
                f"OTM strike {otm_strike} ({self.otm_strikes} strikes OTM). "
                f"SL={self.sl_pct}%, Target={self.target_pct}%."
            )
        else:
            self.logger.debug(
                "[%s] %s – no expiry play (bull=%d bear=%d trend=%s)",
                symbol, self.name, bullish_score, bearish_score, trend,
            )
            return None

        # --- Gate 6: confidence threshold ---
        if confidence < self.min_confidence:
            self.logger.info(
                "[%s] %s – confidence %.1f below threshold %.1f, skipping",
                symbol, self.name, confidence, self.min_confidence,
            )
            return None

        signal = self._build_signal(
            symbol=symbol,
            direction=direction,
            option_type=option_type,
            strike=otm_strike,
            confidence=confidence,
            reason=reason,
            indicators=indicators_snapshot,
        )

        self.logger.info(
            "[%s] %s signal: %s %s @ strike %d (confidence=%.1f) [EXPIRY DAY %s]",
            symbol, self.name, direction, option_type, otm_strike, confidence,
            now.strftime("%Y-%m-%d"),
        )
        return signal

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_expiry_day(now: datetime) -> bool:
        """Check if today is a weekly expiry day (Thursday).

        NIFTY and BANKNIFTY weekly expiry is on Thursday in India.

        Parameters
        ----------
        now : datetime
            Current datetime (assumed IST if the server runs in IST).

        Returns
        -------
        bool
            ``True`` if the weekday is Thursday (``now.weekday() == 3``).
        """
        return now.weekday() == 3  # Monday=0, Thursday=3

    @staticmethod
    def _latest_valid(values: List[float]) -> float:
        """Return the most recent non-NaN value from an EMA list."""
        for v in reversed(values):
            if not math.isnan(v):
                return v
        raise ValueError("No valid (non-NaN) values in list")

    def _select_otm_strike(self, close: float, option_type: str) -> int:
        """Select an OTM strike ``self.otm_strikes`` away from ATM.

        Uses 50-point steps (NIFTY) by default.  For BANKNIFTY the
        step should be 100, but we detect the symbol from context.
        Since this strategy class does not hold a symbol reference during
        strike selection, we use 50 as default.  The caller (trading
        engine) should re-validate strike selection via the option chain
        analyser.
        """
        # Infer step from price magnitude
        step = 100 if close > 30000 else 50
        atm = round(close / step) * step
        if option_type == "CE":
            return int(atm + step * self.otm_strikes)
        else:
            return int(atm - step * self.otm_strikes)

    def calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """Not used directly – confidence is calculated inline in ``analyze``."""
        return super().calculate_confidence(indicators)
