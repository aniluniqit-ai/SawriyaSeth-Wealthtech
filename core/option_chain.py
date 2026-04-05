"""
option_chain.py - Options Chain Analyzer

JSS Sawriya Seth Wealthtech
Analyzes the NSE option chain (OI, premium, IV) to select the
optimal strike and option type for a given trading signal.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lot multipliers used for trade-value calculation
_LOT_MULTIPLIER: dict[str, int] = {
    "NIFTY": 50,
    "BANKNIFTY": 25,
    "FINNIFTY": 50,
}


class OptionChainAnalyzer:
    """Analyses the option chain to derive sentiment, find optimal strikes,
    and enrich trading signals with strike + option-type selections.

    Args:
        broker: A broker instance (e.g. :class:`KotakNeoBroker`) that
                provides ``get_option_chain``, ``get_atm_strike``,
                and ``get_ltp`` methods.
    """

    def __init__(self, broker: Any) -> None:
        self._broker = broker
        self._cache: dict[str, tuple[list[dict[str, Any]], datetime]] = {}
        self._cache_ttl_seconds: int = 30  # refresh cache every 30 s

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def get_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch the full option chain for *symbol*.

        Args:
            symbol:     Underlying (e.g. ``"NIFTY"``, ``"BANKNIFTY"``).
            expiry:     Expiry date (``YYYY-MM-DD``).  ``None`` → next weekly.
            use_cache:  Whether to serve from the in-memory cache.

        Returns:
            List of option-chain dicts.
        """
        symbol = symbol.upper()

        if use_cache:
            cached = self._cache.get(symbol)
            if cached is not None:
                data, ts = cached
                age = (datetime.now() - ts).total_seconds()
                if age < self._cache_ttl_seconds:
                    logger.debug(
                        "Option chain cache hit for %s (age=%.1fs)", symbol, age
                    )
                    return data

        chain = self._broker.get_option_chain(symbol, expiry)
        self._cache[symbol] = (chain, datetime.now())
        logger.info(
            "Option chain fetched for %s: %d strikes", symbol, len(chain)
        )
        return chain

    def get_atm_strike(self, symbol: str) -> int:
        """Get the current ATM strike for *symbol*.

        Args:
            symbol: Underlying symbol.

        Returns:
            Integer ATM strike price.
        """
        return self._broker.get_atm_strike(symbol)

    def get_nearby_strikes(
        self,
        symbol: str,
        num: int = 5,
    ) -> list[int]:
        """Return *num* strikes above and below ATM (sorted ascending).

        Args:
            symbol: Underlying symbol.
            num:    Number of strikes on each side of ATM.

        Returns:
            Sorted list of strike prices.
        """
        atm = self.get_atm_strike(symbol)
        chain = self.get_chain(symbol)

        if not chain:
            logger.warning("Empty chain for %s; returning [ATM]", symbol)
            return [atm]

        strikes = sorted(set(item["strike"] for item in chain))

        # Find ATM index
        try:
            idx = strikes.index(atm)
        except ValueError:
            # ATM not in chain; find closest
            idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))

        lo = max(0, idx - num)
        hi = min(len(strikes), idx + num + 1)
        nearby = strikes[lo:hi]

        logger.info(
            "Nearby strikes for %s (ATM=%d, num=%d): %s",
            symbol, atm, num, nearby,
        )
        return nearby

    # ------------------------------------------------------------------
    # OI Analysis
    # ------------------------------------------------------------------

    def analyze_oi(self, symbol: str) -> dict[str, Any]:
        """Analyse Open Interest data to determine sentiment.

        Logic:
        - Find strike with maximum CE OI (resistance) and PE OI (support).
        - Compute total CE/PE OI and put-call ratio.
        - Sentiment:
          - PCR > 1.2 → ``BULLISH`` (more PE writers → support expected)
          - PCR < 0.8 → ``BEARISH``
          - Otherwise   → ``NEUTRAL``

        Args:
            symbol: Underlying symbol.

        Returns:
            Dict with keys: ``max_ce_oi_strike``, ``max_pe_oi_strike``,
            ``ce_oi_total``, ``pe_oi_total``, ``put_call_ratio``, ``sentiment``.
        """
        chain = self.get_chain(symbol)

        if not chain:
            logger.warning("Cannot analyse OI – empty chain for %s", symbol)
            return {
                "max_ce_oi_strike": 0,
                "max_pe_oi_strike": 0,
                "ce_oi_total": 0,
                "pe_oi_total": 0,
                "put_call_ratio": 0.0,
                "sentiment": "NEUTRAL",
            }

        max_ce_oi = 0
        max_ce_oi_strike = 0
        max_pe_oi = 0
        max_pe_oi_strike = 0
        ce_oi_total = 0
        pe_oi_total = 0

        for item in chain:
            ce_oi = item.get("ce_oi", 0)
            pe_oi = item.get("pe_oi", 0)
            ce_oi_total += ce_oi
            pe_oi_total += pe_oi

            if ce_oi > max_ce_oi:
                max_ce_oi = ce_oi
                max_ce_oi_strike = int(item["strike"])

            if pe_oi > max_pe_oi:
                max_pe_oi = pe_oi
                max_pe_oi_strike = int(item["strike"])

        pcr = pe_oi_total / ce_oi_total if ce_oi_total > 0 else 0.0

        if pcr > 1.2:
            sentiment = "BULLISH"
        elif pcr < 0.8:
            sentiment = "BEARISH"
        else:
            sentiment = "NEUTRAL"

        result = {
            "max_ce_oi_strike": max_ce_oi_strike,
            "max_pe_oi_strike": max_pe_oi_strike,
            "ce_oi_total": ce_oi_total,
            "pe_oi_total": pe_oi_total,
            "put_call_ratio": round(pcr, 4),
            "sentiment": sentiment,
        }

        logger.info(
            "OI analysis for %s: PCR=%.2f, sentiment=%s, maxCE_OI@%d, maxPE_OI@%d",
            symbol, pcr, sentiment, max_ce_oi_strike, max_pe_oi_strike,
        )
        return result

    # ------------------------------------------------------------------
    # Premium Analysis
    # ------------------------------------------------------------------

    def analyze_premium(self, symbol: str) -> dict[str, Any]:
        """Analyse option premium at ATM and identify cheapest options.

        Returns:
            Dict with keys: ``atm_ce_premium``, ``atm_pe_premium``,
            ``iv_skew``, ``cheapest_ce``, ``cheapest_pe``.
        """
        chain = self.get_chain(symbol)
        atm = self.get_atm_strike(symbol)

        if not chain:
            logger.warning("Cannot analyse premium – empty chain for %s", symbol)
            return {
                "atm_ce_premium": 0.0,
                "atm_pe_premium": 0.0,
                "iv_skew": 0.0,
                "cheapest_ce": {"strike": 0, "premium": 0.0, "iv": 0.0},
                "cheapest_pe": {"strike": 0, "premium": 0.0, "iv": 0.0},
            }

        atm_ce_premium = 0.0
        atm_pe_premium = 0.0
        cheapest_ce: dict[str, Any] = {"strike": 0, "premium": float("inf"), "iv": 0.0}
        cheapest_pe: dict[str, Any] = {"strike": 0, "premium": float("inf"), "iv": 0.0}

        atm_ce_iv = 0.0
        atm_pe_iv = 0.0

        for item in chain:
            strike = int(item["strike"])

            # ATM premiums
            if strike == atm:
                atm_ce_premium = item.get("ce_ltp", 0)
                atm_pe_premium = item.get("pe_ltp", 0)
                atm_ce_iv = item.get("ce_iv", 0)
                atm_pe_iv = item.get("pe_iv", 0)

            # Cheapest CE (positive premium)
            ce_premium = item.get("ce_ltp", 0)
            if 0 < ce_premium < cheapest_ce["premium"]:
                cheapest_ce = {
                    "strike": strike,
                    "premium": ce_premium,
                    "iv": item.get("ce_iv", 0),
                }

            # Cheapest PE
            pe_premium = item.get("pe_ltp", 0)
            if 0 < pe_premium < cheapest_pe["premium"]:
                cheapest_pe = {
                    "strike": strike,
                    "premium": pe_premium,
                    "iv": item.get("pe_iv", 0),
                }

        if cheapest_ce["premium"] == float("inf"):
            cheapest_ce = {"strike": 0, "premium": 0.0, "iv": 0.0}
        if cheapest_pe["premium"] == float("inf"):
            cheapest_pe = {"strike": 0, "premium": 0.0, "iv": 0.0}

        iv_skew = round(atm_ce_iv - atm_pe_iv, 4) if (atm_ce_iv or atm_pe_iv) else 0.0

        result = {
            "atm_ce_premium": round(atm_ce_premium, 2),
            "atm_pe_premium": round(atm_pe_premium, 2),
            "iv_skew": iv_skew,
            "cheapest_ce": cheapest_ce,
            "cheapest_pe": cheapest_pe,
        }

        logger.info(
            "Premium analysis for %s: ATM_CE=%.2f, ATM_PE=%.2f, IV_skew=%.2f",
            symbol, atm_ce_premium, atm_pe_premium, iv_skew,
        )
        return result

    # ------------------------------------------------------------------
    # Single option lookup
    # ------------------------------------------------------------------

    def get_option_data(
        self,
        symbol: str,
        strike: int,
        option_type: str,
    ) -> dict[str, Any]:
        """Get LTP, OI, volume, IV for a specific option contract.

        Args:
            symbol:      Underlying symbol.
            strike:      Strike price.
            option_type: ``"CE"`` or ``"PE"``.

        Returns:
            Dict with ``ltp``, ``oi``, ``volume``, ``iv``, ``change_oi``,
            ``change``.  All zeros on failure.
        """
        chain = self.get_chain(symbol)
        option_type = option_type.upper()

        for item in chain:
            if int(item["strike"]) == strike:
                suffix = option_type.lower()
                return {
                    "ltp": item.get(f"{suffix}_ltp", 0),
                    "oi": item.get(f"{suffix}_oi", 0),
                    "volume": item.get(f"{suffix}_volume", 0),
                    "iv": item.get(f"{suffix}_iv", 0),
                    "change_oi": item.get(f"{suffix}_change_oi", 0),
                    "change": item.get(f"{suffix}_change", 0),
                }

        logger.warning(
            "Option not found: %s %s %d", symbol, option_type, strike
        )
        return {
            "ltp": 0, "oi": 0, "volume": 0, "iv": 0,
            "change_oi": 0, "change": 0,
        }

    # ------------------------------------------------------------------
    # Signal enrichment – best strike selection
    # ------------------------------------------------------------------

    def find_best_option(self, signal: dict[str, Any]) -> dict[str, Any]:
        """Given a trading signal, determine the optimal strike and
        optionally refine the option type.

        Selection criteria (scored, highest wins):
        1. **Distance from ATM**: Prefer 1–2 strikes OTM for better
           premium-to-risk ratio.
        2. **OI support**: Prefer strikes near max PE OI (support) for
           CE buys, or near max CE OI (resistance) for PE buys.
        3. **IV**: Prefer moderate IV (not extremely high or low).
        4. **Premium affordability**: Lower premium is preferred for
           smaller capital outlay.

        Args:
            signal: Trading signal dict.  Must contain ``symbol``,
                    ``direction``, ``option_type``, ``confidence``.

        Returns:
            Updated signal dict with ``strike`` and ``option_type``
            added/modified, along with ``selection_reason``.
        """
        symbol = signal.get("symbol", "NIFTY").upper()
        direction = signal.get("direction", "BUY").upper()
        suggested_ot = signal.get("option_type", "CE").upper()

        chain = self.get_chain(symbol)
        atm = self.get_atm_strike(symbol)
        oi_analysis = self.analyze_oi(symbol)

        if not chain:
            logger.warning("Cannot find best option – empty chain for %s", symbol)
            signal["strike"] = atm
            signal["selection_reason"] = "Fallback to ATM (no chain data)"
            return signal

        # Determine step size for OTM strikes
        step = 100 if symbol == "BANKNIFTY" else 50

        # Score each candidate strike
        candidates: list[dict[str, Any]] = []

        for item in chain:
            strike = int(item["strike"])
            ltp_key = f"{suggested_ot.lower()}_ltp"
            iv_key = f"{suggested_ot.lower()}_iv"
            oi_key = f"{suggested_ot.lower()}_oi"
            premium = item.get(ltp_key, 0)

            # Skip zero-premium or deep OTM options
            if premium <= 0:
                continue

            # Distance from ATM in number of strikes
            distance_strikes = abs(strike - atm) / step

            # Only consider strikes within 6 steps of ATM
            if distance_strikes > 6:
                continue

            score = 0.0

            # 1. Prefer 1–2 strikes OTM (lower cost, better risk/reward)
            if 1 <= distance_strikes <= 2:
                score += 40
            elif distance_strikes == 0:
                score += 20  # ATM is okay but expensive
            elif 3 <= distance_strikes <= 4:
                score += 25
            else:
                score += 10  # 5–6 strikes OTM

            # 2. OI proximity bonus
            if direction == "BUY" and suggested_ot == "CE":
                # For CE buys, prefer strikes near PE OI support
                pe_support = oi_analysis["max_pe_oi_strike"]
                oi_dist = abs(strike - pe_support) / step
                score += max(0, 30 - oi_dist * 10)
            elif direction == "BUY" and suggested_ot == "PE":
                # For PE buys, prefer strikes near CE OI resistance
                ce_resist = oi_analysis["max_ce_oi_strike"]
                oi_dist = abs(strike - ce_resist) / step
                score += max(0, 30 - oi_dist * 10)

            # 3. Moderate IV bonus (15–40 range is ideal)
            iv = item.get(iv_key, 0)
            if 15 <= iv <= 40:
                score += 20
            elif iv > 40:
                score += 5  # High IV = expensive
            else:
                score += 10

            # 4. Lower premium bonus (affordability)
            if premium < 100:
                score += 15
            elif premium < 200:
                score += 10
            else:
                score += 5

            # 5. OI concentration bonus (higher OI = more liquid)
            oi = item.get(oi_key, 0)
            if oi > 0:
                score += min(10, oi / 100_000)

            candidates.append({
                "strike": strike,
                "premium": premium,
                "iv": iv,
                "oi": oi,
                "distance": distance_strikes,
                "score": score,
            })

        if not candidates:
            # Fallback
            signal["strike"] = atm
            signal["selection_reason"] = "Fallback to ATM (no valid candidates)"
            return signal

        # Sort by score descending
        candidates.sort(key=lambda c: c["score"], reverse=True)
        best = candidates[0]

        # Validate: for BUY CE, prefer OTM (strike > spot); for BUY PE, OTM (strike < spot)
        # Adjust if needed
        ltp = self._broker.get_ltp(symbol)
        if ltp > 0:
            if suggested_ot == "CE" and best["strike"] <= ltp * 0.99:
                # Try to find a strike above spot
                otm_ce = [c for c in candidates if c["strike"] > ltp]
                if otm_ce:
                    best = otm_ce[0]
            elif suggested_ot == "PE" and best["strike"] >= ltp * 1.01:
                # Try to find a strike below spot
                otm_pe = [c for c in candidates if c["strike"] < ltp]
                if otm_pe:
                    best = otm_pe[0]

        signal["strike"] = best["strike"]
        signal["entry_price"] = best["premium"]
        signal["selection_reason"] = (
            f"Best strike: {best['strike']} (score={best['score']:.1f}, "
            f"premium={best['premium']:.2f}, IV={best['iv']:.1f}, "
            f"dist={best['distance']:.1f})"
        )

        logger.info(
            "Best option for %s %s %s → strike=%d @ %.2f (score=%.1f)",
            direction, symbol, suggested_ot,
            best["strike"], best["premium"], best["score"],
        )
        return signal

    # ------------------------------------------------------------------
    # Lot size / multiplier
    # ------------------------------------------------------------------

    @staticmethod
    def get_lot_multiplier(symbol: str) -> int:
        """Return the lot multiplier for the given symbol.

        - NIFTY     → 50
        - BANKNIFTY → 25
        - FINNIFTY  → 50
        - default   → 50

        Args:
            symbol: Underlying symbol.

        Returns:
            Integer lot multiplier.
        """
        return _LOT_MULTIPLIER.get(symbol.upper(), 50)
