"""
core - JSS Sawriya Seth Wealthtech Core Trading Modules

This package provides the foundational building blocks for the AI options
trading platform:

- ``engine``         – Main trading engine (brain of the system)
- ``db_helper``      – Thread-safe SQLite persistence layer
- ``indicators``     – Pure-Python + numpy technical indicators
- ``option_chain``   – Options chain analysis (OI, premium, strike selection)
- ``capital``        – Capital management with ₹100 hard floor
- ``risk``           – Risk management (SL, target, trailing, cooldowns)
"""

from .engine import TradingEngine
from .db_helper import Database
from .indicators import (
    adx,
    atr,
    bollinger_bands,
    ema,
    get_trend,
    is_sideways,
    macd,
    rsi,
    sma,
    supertrend,
    vwap,
)
from .option_chain import OptionChainAnalyzer
from .capital import CapitalManager, HARD_FLOOR
from .risk import RiskManager

__all__ = [
    "TradingEngine",
    "Database",
    "adx",
    "atr",
    "bollinger_bands",
    "CapitalManager",
    "ema",
    "get_trend",
    "HARD_FLOOR",
    "is_sideways",
    "macd",
    "OptionChainAnalyzer",
    "RiskManager",
    "rsi",
    "sma",
    "supertrend",
    "vwap",
]
