"""
base_strategy.py - Abstract Base Strategy Class

JSS Sawriya Seth Wealthtech
Provides the contract that every concrete trading strategy must follow.
All strategies inherit from ``BaseStrategy`` and implement the ``analyze``
method to produce ``Signal`` dicts when entry conditions are met.

Signal dict schema:
    {
        "direction":  "BUY" | "SELL",
        "option_type": "CE" | "PE",
        "strike":     int,
        "symbol":     str,
        "confidence": float (0-100),
        "reason":     str,
        "strategy_name": str,
        "indicators": dict,
        "timestamp":  datetime,
    }

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Base class for all trading strategies.

    Subclasses must override :meth:`analyze` and may override
    :meth:`calculate_confidence` for custom confidence scoring.

    Parameters
    ----------
    name : str
        Human-readable strategy name (e.g. ``"Momentum Follow"``).
    config : dict
        Strategy-specific configuration merged with global defaults.
        Expected keys:
            - ``min_confidence`` (float, default 65)
            - Any other keys consumed by the subclass.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self.min_confidence: float = config.get("min_confidence", 65.0)
        self.logger = logging.getLogger(f"strategy.{name}")

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def analyze(self, symbol: str, candles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Analyze market data and optionally generate a trading signal.

        Implementations **must** verify all of the following before
        producing a signal:

        1. At least **30 candles** are provided.
        2. The market is **not sideways** (call ``is_sideways``).
        3. A **clear trend** exists (call ``get_trend``).
        4. **All** strategy-specific indicator conditions are satisfied.
        5. The resulting **confidence** >= ``self.min_confidence``.

        If any condition fails the method must return ``None`` (no trade).

        Parameters
        ----------
        symbol : str
            Instrument symbol (e.g. ``"NIFTY"``).
        candles : list[dict]
            List of OHLCV candle dicts ordered oldest → newest.

        Returns
        -------
        dict | None
            A fully populated Signal dict, or ``None`` if no trade is
            warranted.
        """
        pass

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def calculate_confidence(self, indicators: Dict[str, Any]) -> float:
        """Calculate a confidence score (0 – 100) based on indicator agreement.

        The default implementation returns 50.  Subclasses should override
        this with a weighted scoring model appropriate to their indicators.

        Parameters
        ----------
        indicators : dict
            Mapping of indicator name → value / bool / dict.

        Returns
        -------
        float
            Confidence between 0 and 100.
        """
        return 50.0

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """Validate that a signal dict contains every required field.

        Parameters
        ----------
        signal : dict
            Candidate signal dict to verify.

        Returns
        -------
        bool
            ``True`` when all required keys are present.
        """
        required: list[str] = [
            "direction",
            "option_type",
            "strike",
            "symbol",
            "confidence",
            "reason",
            "strategy_name",
            "timestamp",
        ]
        return all(key in signal for key in required)

    def _build_signal(
        self,
        symbol: str,
        direction: str,
        option_type: str,
        strike: int,
        confidence: float,
        reason: str,
        indicators: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct a standard Signal dict with all required fields.

        This is a convenience factory for subclasses so that every signal
        conforms to the expected schema automatically.

        Parameters
        ----------
        symbol : str
        direction : ``"BUY"`` or ``"SELL"``
        option_type : ``"CE"`` or ``"PE"``
        strike : int
        confidence : float
        reason : str
        indicators : dict
            Indicator values to attach to the signal for logging / UI.

        Returns
        -------
        dict
            Fully populated Signal dict.
        """
        signal: Dict[str, Any] = {
            "direction": direction,
            "option_type": option_type,
            "strike": strike,
            "symbol": symbol,
            "confidence": round(confidence, 2),
            "reason": reason,
            "strategy_name": self.name,
            "indicators": indicators,
            "timestamp": datetime.now(),
        }
        return signal

    def _check_data_sufficiency(self, candles: List[Dict[str, Any]], min_candles: int = 30) -> bool:
        """Return ``True`` when there are enough candles to analyze.

        Parameters
        ----------
        candles : list[dict]
        min_candles : int
            Minimum candle count (default 30).

        Returns
        -------
        bool
        """
        if len(candles) < min_candles:
            self.logger.debug(
                "Insufficient candles: got %d, need ≥ %d", len(candles), min_candles
            )
            return False
        return True
