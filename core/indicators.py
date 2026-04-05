"""
indicators.py - Technical Indicators Module

JSS Sawriya Seth Wealthtech
Pure-Python + numpy technical indicator library for the options trading
engine.  Every function accepts a list of candle dicts (OHLCV) and
returns calculated values.  Edge cases (insufficient data) return None
gracefully.

NO external ta-library dependency – all math is implemented from scratch.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ===================================================================
# Helpers
# ===================================================================

def _closes(candles: list[dict[str, Any]]) -> np.ndarray:
    """Extract closing prices as a float64 numpy array."""
    if not candles:
        return np.array([], dtype=np.float64)
    return np.array([c["close"] for c in candles], dtype=np.float64)


def _highs(candles: list[dict[str, Any]]) -> np.ndarray:
    return np.array([c["high"] for c in candles], dtype=np.float64)


def _lows(candles: list[dict[str, Any]]) -> np.ndarray:
    return np.array([c["low"] for c in candles], dtype=np.float64)


def _volumes(candles: list[dict[str, Any]]) -> np.ndarray:
    return np.array([c["volume"] for c in candles], dtype=np.float64)


def _true_range(candles: list[dict[str, Any]]) -> np.ndarray:
    """Compute True Range for each candle (starting from index 1)."""
    if len(candles) < 2:
        return np.array([], dtype=np.float64)
    highs = _highs(candles)
    lows = _lows(candles)
    prev_close = _closes(candles)[:-1]
    tr1 = highs[1:] - lows[1:]
    tr2 = np.abs(highs[1:] - prev_close)
    tr3 = np.abs(lows[1:] - prev_close)
    return np.maximum(np.maximum(tr1, tr2), tr3)


# ===================================================================
# Moving Averages
# ===================================================================

def sma(candles: list[dict[str, Any]], period: int) -> Optional[list[float]]:
    """Simple Moving Average.

    Returns a list of length ``len(candles)`` where the first
    ``period - 1`` entries are ``None`` (insufficient data).

    Args:
        candles: OHLCV candle dicts.
        period:  Look-back window.

    Returns:
        List of floats (or None values) for each candle position.
    """
    if len(candles) < period or period <= 0:
        return None

    closes = _closes(candles)
    result: list[float] = []

    # Use cumulative sum for O(n) computation
    cumsum = np.cumsum(closes)
    for i in range(len(candles)):
        if i < period - 1:
            result.append(float("nan"))
        elif i == period - 1:
            result.append(float(cumsum[i] / period))
        else:
            result.append(float((cumsum[i] - cumsum[i - period]) / period))

    return result


def ema(candles: list[dict[str, Any]], period: int) -> Optional[list[float]]:
    """Exponential Moving Average.

    Returns a list of length ``len(candles)`` where the first
    ``period - 1`` entries are ``None``.

    Args:
        candles: OHLCV candle dicts.
        period:  Look-back window.

    Returns:
        List of floats (or NaN) for each candle position.
    """
    if len(candles) < period or period <= 0:
        return None

    closes = _closes(candles)
    k = 2.0 / (period + 1)
    result: list[float] = [float("nan")] * (period - 1)

    # Seed EMA with SMA of first `period` closes
    seed = float(np.mean(closes[:period]))
    result.append(seed)

    for i in range(period, len(closes)):
        val = closes[i] * k + result[-1] * (1 - k)
        result.append(val)

    return result


# ===================================================================
# Oscillators
# ===================================================================

def rsi(candles: list[dict[str, Any]], period: int = 14) -> Optional[float]:
    """Relative Strength Index (Wilder's smoothing method).

    Args:
        candles: OHLCV candle dicts.
        period:  Look-back window (default 14).

    Returns:
        RSI value (0–100) for the latest candle, or ``None`` if
        insufficient data.
    """
    if len(candles) < period + 1:
        return None

    closes = _closes(candles)
    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Initial average gain/loss (simple mean of first `period` values)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Wilder's smoothing
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def macd(
    candles: list[dict[str, Any]],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[dict[str, Any]]:
    """MACD (Moving Average Convergence Divergence).

    Args:
        candles: OHLCV candle dicts.
        fast:    Fast EMA period (default 12).
        slow:    Slow EMA period (default 26).
        signal:  Signal line EMA period (default 9).

    Returns:
        Dict with keys ``macd_line``, ``signal_line``, ``histogram``
        (all floats), or ``None`` if insufficient data.
    """
    if len(candles) < slow + signal:
        return None

    fast_ema = ema(candles, fast)
    slow_ema = ema(candles, slow)
    if fast_ema is None or slow_ema is None:
        return None

    macd_line_arr = [
        f - s if not (math.isnan(f) or math.isnan(s)) else float("nan")
        for f, s in zip(fast_ema, slow_ema)
    ]

    # Signal line = EMA of MACD line values
    valid_start = slow - 1  # first valid index where both EMAs have values
    macd_candles = [{"close": v} for v in macd_line_arr[valid_start:] if not math.isnan(v)]
    if len(macd_candles) < signal:
        return None

    signal_ema = ema(macd_candles, signal)
    if signal_ema is None:
        return None

    latest_macd = macd_line_arr[-1]
    latest_signal = signal_ema[-1]
    histogram = latest_macd - latest_signal

    return {
        "macd_line": round(latest_macd, 4),
        "signal_line": round(latest_signal, 4),
        "histogram": round(histogram, 4),
    }


# ===================================================================
# Volatility / Bands
# ===================================================================

def bollinger_bands(
    candles: list[dict[str, Any]],
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[dict[str, Any]]:
    """Bollinger Bands.

    Args:
        candles: OHLCV candle dicts.
        period:  SMA period (default 20).
        std_dev: Standard deviation multiplier (default 2.0).

    Returns:
        Dict with keys ``upper``, ``middle``, ``lower``, ``bandwidth``,
        or ``None`` if insufficient data.
    """
    if len(candles) < period or period <= 0:
        return None

    closes = _closes(candles)
    middle = float(np.mean(closes[-period:]))
    std = float(np.std(closes[-period:], ddof=0))
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    bandwidth = (upper - lower) / middle if middle != 0 else 0.0

    return {
        "upper": round(upper, 2),
        "middle": round(middle, 2),
        "lower": round(lower, 2),
        "bandwidth": round(bandwidth, 6),
    }


def atr(candles: list[dict[str, Any]], period: int = 14) -> Optional[float]:
    """Average True Range.

    Uses Wilder's smoothing (exponential) for the ATR.

    Args:
        candles: OHLCV candle dicts.
        period:  Look-back window (default 14).

    Returns:
        ATR value (float), or ``None`` if insufficient data.
    """
    if len(candles) < period + 1:
        return None

    tr = _true_range(candles)
    if len(tr) == 0:
        return None

    # Initial ATR = SMA of first `period` TR values
    atr_val = float(np.mean(tr[:period]))

    # Wilder's smoothing
    for i in range(period, len(tr)):
        atr_val = (atr_val * (period - 1) + tr[i]) / period

    return round(atr_val, 2)


def supertrend(
    candles: list[dict[str, Any]],
    period: int = 10,
    multiplier: float = 3.0,
) -> Optional[list[dict[str, str | float]]]:
    """Supertrend indicator.

    Args:
        candles:    OHLCV candle dicts.
        period:     ATR period (default 10).
        multiplier: ATR multiplier (default 3.0).

    Returns:
        List of dicts ``[{value: float, direction: "UP"/"DOWN"}, …]``
        aligned with the input candles.  The first ``period`` entries
        have ``direction: "UP"`` as placeholders.
    """
    if len(candles) < period + 1 or period <= 0:
        return None

    closes = _closes(candles)
    highs = _highs(candles)
    lows = _lows(candles)

    # Compute ATR for the full series using simple SMA rolling method
    tr = _true_range(candles)
    atr_values: list[float] = []
    for i in range(len(tr)):
        start = max(0, i - period + 1)
        atr_values.append(float(np.mean(tr[start:i + 1])))

    # Prepend NaN for the first candle (no TR)
    # tr has len-1 entries, so we insert a NaN at the front
    full_atr = [float("nan")] + atr_values

    result: list[dict[str, str | float]] = []

    prev_upper_band = 0.0
    prev_lower_band = 0.0
    prev_supertrend = 0.0
    prev_direction = "UP"

    for i in range(len(candles)):
        if i < period or math.isnan(full_atr[i]):
            result.append({"value": float("nan"), "direction": "UP"})
            continue

        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * full_atr[i]
        basic_lower = hl2 - multiplier * full_atr[i]

        # Adjust bands: upper band should not rise, lower band should not fall
        if i > period:
            upper_band = min(basic_upper, prev_upper_band) if basic_upper < prev_upper_band or closes[i - 1] > prev_upper_band else basic_upper
            lower_band = max(basic_lower, prev_lower_band) if basic_lower > prev_lower_band or closes[i - 1] < prev_lower_band else basic_lower
        else:
            upper_band = basic_upper
            lower_band = basic_lower

        prev_upper_band = upper_band
        prev_lower_band = lower_band

        # Determine direction
        if prev_supertrend == prev_upper_band:
            direction = "DOWN"
        else:
            direction = "UP"

        # Flip direction on cross
        if direction == "UP" and closes[i] < lower_band:
            direction = "DOWN"
        elif direction == "DOWN" and closes[i] > upper_band:
            direction = "UP"

        st_value = lower_band if direction == "UP" else upper_band
        prev_supertrend = st_value
        prev_direction = direction

        result.append({"value": round(st_value, 2), "direction": direction})

    return result


# ===================================================================
# Volume indicators
# ===================================================================

def vwap(candles: list[dict[str, Any]]) -> Optional[float]:
    """Volume Weighted Average Price.

    Computes cumulative volume-weighted average over all provided
    candles.

    Args:
        candles: OHLCV candle dicts.

    Returns:
        VWAP value (float), or ``None`` if no candles or zero volume.
    """
    if not candles:
        return None

    closes = _closes(candles)
    volumes = _volumes(candles)
    typical_prices = (closes + _highs(candles) + _lows(candles)) / 3.0

    total_vp = float(np.sum(typical_prices * volumes))
    total_vol = float(np.sum(volumes))

    if total_vol == 0:
        return None

    return round(total_vp / total_vol, 2)


# ===================================================================
# Trend indicators
# ===================================================================

def adx(candles: list[dict[str, Any]], period: int = 14) -> Optional[float]:
    """Average Directional Index.

    Measures trend strength on a 0–100 scale.  Values above 25
    typically indicate a strong trend; below 20 → sideways.

    Args:
        candles: OHLCV candle dicts.
        period:  Look-back window (default 14).

    Returns:
        ADX value (float), or ``None`` if insufficient data.
    """
    if len(candles) < 2 * period + 1:
        return None

    highs = _highs(candles)
    lows = _lows(candles)
    closes = _closes(candles)

    # +DM and -DM
    plus_dm = np.zeros(len(candles))
    minus_dm = np.zeros(len(candles))
    tr = np.zeros(len(candles))

    for i in range(1, len(candles)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # Wilder's smoothing
    smooth_plus_dm = float(np.sum(plus_dm[1:period + 1]))
    smooth_minus_dm = float(np.sum(minus_dm[1:period + 1]))
    smooth_tr = float(np.sum(tr[1:period + 1]))

    dx_list: list[float] = []

    for i in range(period + 1, len(candles)):
        smooth_plus_dm = smooth_plus_dm - (smooth_plus_dm / period) + plus_dm[i]
        smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / period) + minus_dm[i]
        smooth_tr = smooth_tr - (smooth_tr / period) + tr[i]

        if smooth_tr == 0:
            continue

        plus_di = 100.0 * (smooth_plus_dm / smooth_tr)
        minus_di = 100.0 * (smooth_minus_dm / smooth_tr)

        di_sum = plus_di + minus_di
        if di_sum == 0:
            continue
        dx = 100.0 * abs(plus_di - minus_di) / di_sum
        dx_list.append(dx)

    if len(dx_list) < period:
        # Not enough DX values for ADX smoothing; return first DX
        return round(dx_list[-1], 2) if dx_list else None

    # ADX = Wilder's smoothed DX
    adx_val = float(np.mean(dx_list[:period]))
    for i in range(period, len(dx_list)):
        adx_val = (adx_val * (period - 1) + dx_list[i]) / period

    return round(adx_val, 2)


def is_sideways(
    candles: list[dict[str, Any]],
    adx_threshold: float = 20.0,
    bb_width_threshold: float = 0.03,
) -> Optional[bool]:
    """Detect sideways / ranging market conditions.

    Market is considered sideways when **both**:
    - ADX < ``adx_threshold`` (weak trend)
    - Bollinger Bandwidth < ``bb_width_threshold`` (low volatility)

    Args:
        candles:             OHLCV candle dicts.
        adx_threshold:       ADX value below which trend is weak (default 20).
        bb_width_threshold:  BB width below which volatility is low (default 0.03).

    Returns:
        ``True`` if the market is sideways, ``False`` if trending,
        or ``None`` if indicators cannot be computed.
    """
    adx_val = adx(candles, period=14)
    bb = bollinger_bands(candles, period=20)

    if adx_val is None or bb is None:
        return None

    sideways = adx_val < adx_threshold and bb["bandwidth"] < bb_width_threshold

    logger.debug(
        "Sideways check: ADX=%.2f (thresh=%.1f), BB_width=%.4f (thresh=%.4f) → %s",
        adx_val, adx_threshold, bb["bandwidth"], bb_width_threshold,
        "SIDEWAYS" if sideways else "TRENDING",
    )
    return sideways


def get_trend(candles: list[dict[str, Any]]) -> Optional[str]:
    """Determine the current market trend using EMA crossover + ADX.

    Classification logic:
    - EMA(9) vs EMA(21) crossover direction → bull/bear
    - ADX strength → STRONG_ prefix (≥ 30) or no prefix

    Returns one of:
    ``"STRONG_BULL"``, ``"BULL"``, ``"NEUTRAL"``, ``"BEAR"``, ``"STRONG_BEAR"``

    Args:
        candles: OHLCV candle dicts.

    Returns:
        Trend string, or ``None`` if insufficient data.
    """
    min_required = 25  # enough for EMA(21) + some buffer
    if len(candles) < min_required:
        return None

    ema_short = ema(candles, 9)
    ema_long = ema(candles, 21)

    if ema_short is None or ema_long is None:
        return None

    # Get latest valid values (skip NaN prefix)
    short_latest = None
    long_latest = None
    for s, l in zip(reversed(ema_short), reversed(ema_long)):
        if math.isnan(s) or math.isnan(l):
            continue
        short_latest = s
        long_latest = l
        break

    if short_latest is None or long_latest is None:
        return None

    adx_val = adx(candles, period=14)
    is_strong = adx_val is not None and adx_val >= 30.0

    if short_latest > long_latest:
        return "STRONG_BULL" if is_strong else "BULL"
    elif short_latest < long_latest:
        return "STRONG_BEAR" if is_strong else "BEAR"
    else:
        return "NEUTRAL"
