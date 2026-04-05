"""
parser.py - Trading Signal Parser for JSS Sawriya Seth Wealthtech

Extracts structured trading signals from raw Telegram messages using regex.
Designed to be lenient — handles messy formatting, emojis, abbreviations,
and common variations found in Indian options trading groups.

Supported signal formats (examples):
    1. "BUY NIFTY 24500 CE" / "SELL BANKNIFTY 51000 PE"
    2. "🟢 NIFTY 24500 CE ABOVE 185"
    3. "SHORT NIFTY 24500 PE SL 190 TGT 170"
    4. "NIFTY CE 24500 @185 SL 181 TGT 195"
    5. Any variation with common trading abbreviations (SL, TGT, TARGET, CMP, ABOVE, BELOW, etc.)
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Known option symbols (uppercase). Expand as needed.
_KNOWN_SYMBOLS = {
    "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY",
    "NIFTY50", "BANKNIFTY50",
}

# Known option types.
_KNOWN_OTYPES = {"CE", "PE", "CALL", "PUT"}

# Known direction keywords and their normalised form.
_DIRECTION_MAP = {
    "buy": "BUY",
    "long": "BUY",
    "b": "BUY",
    "sell": "SELL",
    "short": "SELL",
    "s": "SELL",
}

# Emoji direction hints.
_EMOJI_BUY = {"🟢", "🟩", "✅", "🟢💰", "bullish", "bull"}
_EMOJI_SELL = {"🔴", "🟥", "❌", "🔻", "bearish", "bear"}

# Regex building blocks.
_RE_NUMBER = r"[\d]+(?:\.\d+)?"  # integer or decimal
_RE_PRICE = r"[\d]+\.?\d*"       # price-like number

# Pre-compiled master pattern — tries to match a full signal in one pass.
# Structure (all optional except symbol + strike + option_type):
#   [direction] [symbol] [strike] [option_type] [@/above/below price] [SL price] [TGT/TARGET price]
_MASTER_RE = re.compile(
    r"(?P<direction>(?:BUY|SELL|SHORT|LONG)\b)?\s*"
    r"(?P<symbol>NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|NIFTY50|BANKNIFTY50)\s*"
    r"(?P<strike>\d{4,5})\s*"
    r"(?P<option_type>CE|PE|CALL|PUT)\b\s*"
    r"(?:"
    r"(?:@|ABOVE|BELOW|CMP|AT|RATE|PRICE|ENTRY)[:\s]*(?P<entry>" + _RE_PRICE + r")\s*"
    r")?"
    r"(?:"
    r"(?:SL|STOPLOSS|STOP\s*LOSS|S\/L)[:\s]*(?P<sl>" + _RE_PRICE + r")\s*"
    r")?"
    r"(?:"
    r"(?:TGT|TARGET|TP|BOOK)[:\s]*(?P<target>" + _RE_PRICE + r")\s*"
    r")?",
    re.IGNORECASE | re.DOTALL,
)

# Simpler pattern for "SYMBOL OTYPE STRIKE @price SL price TGT price" form.
_ALT_RE = re.compile(
    r"(?P<symbol>NIFTY|BANKNIFTY|FINNIFTY|MIDCPNIFTY|NIFTY50|BANKNIFTY50)\s*"
    r"(?P<option_type>CE|PE|CALL|PUT)\s*"
    r"(?P<strike>\d{4,5})\s*"
    r"(?:@|ABOVE|BELOW|CMP|AT|RATE|PRICE|ENTRY)[:\s]*(?P<entry>" + _RE_PRICE + r")\s*"
    r"(?:SL|STOPLOSS|STOP\s*LOSS|S\/L)[:\s]*(?P<sl>" + _RE_PRICE + r")\s*"
    r"(?:TGT|TARGET|TP|BOOK)[:\s]*(?P<target>" + _RE_PRICE + r")\s*",
    re.IGNORECASE | re.DOTALL,
)


class SignalParser:
    """Parse trading signals from raw Telegram messages.

    Usage::

        parser = SignalParser()
        signal = parser.parse("BUY NIFTY 24500 CE SL 181 TGT 195")
        if signal:
            print(signal)  # {'direction': 'BUY', 'symbol': 'NIFTY', ...}
    """

    def __init__(self) -> None:
        self._patterns = [_MASTER_RE, _ALT_RE]
        logger.info("SignalParser initialised with %d patterns", len(self._patterns))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, message_text: str) -> dict[str, Any] | None:
        """Parse a message and return a signal dict, or *None* if no signal
        is detected.

        The returned dict has the following keys (all strings unless noted):

        - ``direction``  – "BUY" or "SELL"
        - ``symbol``     – e.g. "NIFTY"
        - ``strike``     – e.g. "24500"
        - ``option_type`` – "CE" or "PE"
        - ``entry_price`` – optional float or ``None``
        - ``sl``         – optional float or ``None``
        - ``target``     – optional float or ``None``
        - ``confidence`` – always ``50`` (Telegram signals start at base confidence)
        - ``reason``     – always ``"Telegram Signal"``
        - ``raw_text``   – the original message text
        """
        if not message_text or not message_text.strip():
            return None

        try:
            cleaned = self._clean_message(message_text)
            direction_hint = self._detect_direction_hint(message_text)

            for pattern in self._patterns:
                match = pattern.search(cleaned)
                if not match:
                    continue

                groups = match.groupdict()
                signal = self._build_signal(groups, direction_hint, message_text)
                if signal is not None:
                    logger.info(
                        "Signal parsed: %s %s %s %s",
                        signal["direction"],
                        signal["symbol"],
                        signal["strike"],
                        signal["option_type"],
                    )
                    return signal

            # If master patterns didn't match, try the aggressive fallback
            signal = self._aggressive_parse(cleaned, direction_hint, message_text)
            if signal:
                return signal

        except Exception as exc:
            logger.error("Error parsing signal: %s", exc, exc_info=True)

        return None

    def validate_signal(self, signal: dict[str, Any]) -> bool:
        """Check if a parsed signal has the minimum required fields.

        Required keys: ``direction``, ``symbol``, ``strike``, ``option_type``.

        Returns:
            ``True`` if the signal is valid and tradeable.
        """
        if not signal or not isinstance(signal, dict):
            return False

        required_keys = {"direction", "symbol", "strike", "option_type"}
        missing = required_keys - set(signal.keys())

        if missing:
            logger.warning("Signal validation failed — missing keys: %s", missing)
            return False

        # Direction must be BUY or SELL
        if signal["direction"] not in ("BUY", "SELL"):
            logger.warning("Signal validation failed — invalid direction: %s", signal["direction"])
            return False

        # Option type must be CE or PE
        if signal["option_type"] not in ("CE", "PE"):
            logger.warning("Signal validation failed — invalid option_type: %s", signal["option_type"])
            return False

        # Strike must be a positive number
        try:
            strike_val = int(signal["strike"])
            if strike_val <= 0:
                raise ValueError
        except (ValueError, TypeError):
            logger.warning("Signal validation failed — invalid strike: %s", signal["strike"])
            return False

        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_message(text: str) -> str:
        """Normalise message text for regex matching.

        - Collapse multiple whitespace / newlines into single space
        - Remove common emojis (keep text)
        - Strip leading/trailing whitespace
        """
        # Remove common trading emojis
        cleaned = re.sub(r"[🟢🔴🟢🟩🟥✅❌🔻📊📂💰🛑🎯🤖📈💵⚡🔥⏰📢📋🏷📝🏦⏳❗]", " ", text)
        # Collapse whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.upper()

    @staticmethod
    def _detect_direction_hint(text: str) -> str | None:
        """Look for emoji or text-based direction hints in the original message."""
        text_upper = text.upper()

        # Check for buy emojis
        for hint in _EMOJI_BUY:
            if hint.upper() in text_upper:
                return "BUY"

        # Check for sell emojis
        for hint in _EMOJI_SELL:
            if hint.upper() in text_upper:
                return "SELL"

        # Check for text keywords
        for keyword, direction in _DIRECTION_MAP.items():
            # Word-boundary match
            if re.search(rf"\b{keyword}\b", text_upper):
                return direction

        return None

    def _build_signal(
        self,
        groups: dict[str, str | None],
        direction_hint: str | None,
        raw_text: str,
    ) -> dict[str, Any] | None:
        """Convert regex groups into a signal dict."""
        symbol = groups.get("symbol")
        strike = groups.get("strike")
        raw_otype = groups.get("option_type", "")

        # Symbol and strike are mandatory
        if not symbol or not strike:
            return None

        # Normalise option type
        option_type = self._normalise_option_type(raw_otype)
        if option_type is None:
            return None

        # Determine direction: explicit > emoji hint > default based on context
        direction = self._resolve_direction(groups.get("direction"), direction_hint)

        # Parse numeric fields
        entry_price = self._safe_float(groups.get("entry"))
        sl = self._safe_float(groups.get("sl"))
        target = self._safe_float(groups.get("target"))

        return {
            "direction": direction,
            "symbol": symbol.upper(),
            "strike": strike,
            "option_type": option_type,
            "entry_price": entry_price,
            "sl": sl,
            "target": target,
            "confidence": 50,
            "reason": "Telegram Signal",
            "raw_text": raw_text,
        }

    @staticmethod
    def _normalise_option_type(raw: str | None) -> str | None:
        """Normalise option type to CE or PE."""
        if not raw:
            return None
        raw = raw.strip().upper()
        if raw in ("CE", "CALL"):
            return "CE"
        if raw in ("PE", "PUT"):
            return "PE"
        return None

    @staticmethod
    def _resolve_direction(
        explicit: str | None, hint: str | None
    ) -> str:
        """Determine trade direction from explicit keyword and/or emoji hint."""
        if explicit:
            normalised = explicit.strip().upper()
            if normalised == "SHORT":
                return "SELL"
            if normalised == "LONG":
                return "BUY"
            if normalised in ("BUY", "SELL"):
                return normalised
        if hint:
            return hint
        # Default to BUY if no direction is specified
        return "BUY"

    @staticmethod
    def _safe_float(value: str | None) -> float | None:
        """Convert a string to float, returning None on failure."""
        if not value:
            return None
        try:
            return float(value.strip())
        except (ValueError, TypeError):
            return None

    def _aggressive_parse(
        self,
        cleaned: str,
        direction_hint: str | None,
        raw_text: str,
    ) -> dict[str, Any] | None:
        """Last-resort parser for unusual formats.

        Looks for any known symbol + strike + option_type combo embedded in
        the text, even if surrounding keywords are garbled.
        """
        try:
            # Find any symbol
            symbol = None
            for sym in _KNOWN_SYMBOLS:
                if sym in cleaned:
                    symbol = sym
                    break

            if not symbol:
                return None

            # Find option type near the symbol
            option_type = None
            for ot in _KNOWN_OTYPES:
                if ot in cleaned:
                    option_type = ot
                    break

            if not option_type:
                return None

            # Find a 4-5 digit number near the symbol (likely a strike)
            # Look for numbers between 5000 and 60000 (reasonable strike range)
            strike_matches = re.findall(r"\b(\d{4,5})\b", cleaned)
            strike = None
            for candidate in strike_matches:
                num = int(candidate)
                if 5000 <= num <= 60000:
                    strike = candidate
                    break

            if not strike:
                return None

            option_type = self._normalise_option_type(option_type)
            if option_type is None:
                return None

            direction = self._resolve_direction(None, direction_hint)

            # Try to grab SL and target from the text
            sl = None
            target = None

            sl_match = re.search(
                r"(?:SL|STOPLOSS|STOP\s*LOSS|S/L)[:\s]*(\d+\.?\d*)",
                cleaned,
            )
            if sl_match:
                sl = self._safe_float(sl_match.group(1))

            tgt_match = re.search(
                r"(?:TGT|TARGET|TP|BOOK)[:\s]*(\d+\.?\d*)",
                cleaned,
            )
            if tgt_match:
                target = self._safe_float(tgt_match.group(1))

            # Try to grab entry price
            entry = None
            entry_match = re.search(
                r"(?:@|ABOVE|BELOW|CMP|AT|RATE|PRICE|ENTRY)[:\s]*(\d+\.?\d*)",
                cleaned,
            )
            if entry_match:
                entry = self._safe_float(entry_match.group(1))

            signal = {
                "direction": direction,
                "symbol": symbol,
                "strike": strike,
                "option_type": option_type,
                "entry_price": entry,
                "sl": sl,
                "target": target,
                "confidence": 50,
                "reason": "Telegram Signal",
                "raw_text": raw_text,
            }

            logger.debug("Aggressive parse produced signal: %s", signal)
            return signal

        except Exception as exc:
            logger.error("Aggressive parse failed: %s", exc, exc_info=True)
            return None
