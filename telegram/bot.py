"""
bot.py - Telegram Alert Bot for JSS Sawriya Seth Wealthtech

Sends trade alerts, daily reports, and error notifications via Telegram.
Uses python-telegram-bot v21+ (async/await) running in a background thread.

All send operations are wrapped in try/except — failures are logged but never
crash the main trading engine.
"""

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


class TelegramAlertBot:
    """Send formatted trade alerts and reports to a Telegram chat.

    The bot runs its own asyncio event loop in a daemon thread so it never
    blocks the main application thread.

    Args:
        token: Bot API token from @BotFather.
        chat_id: Numeric chat ID (or channel username) to send messages to.
    """

    def __init__(self, token: str, chat_id: str | int) -> None:
        self._token = token
        self._chat_id = chat_id
        self._bot: Bot | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the bot in a background daemon thread.

        If the bot is already running this is a no-op.
        """
        if self._running:
            logger.warning("TelegramAlertBot is already running")
            return

        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="tg-alert-bot",
            daemon=True,
        )
        self._thread.start()
        logger.info("TelegramAlertBot started in background thread")

    def _run_event_loop(self) -> None:
        """Coroutine runner — lives inside the daemon thread."""
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._bot = Bot(token=self._token)
        try:
            # Run a forever-future so the loop stays alive
            self._loop.run_forever()
        except Exception as exc:
            logger.error("TelegramAlertBot event loop crashed: %s", exc, exc_info=True)
        finally:
            self._running = False
            self._loop = None

    def stop(self) -> None:
        """Gracefully stop the bot and join the background thread."""
        if not self._running:
            return

        self._running = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("TelegramAlertBot stopped")

    # ------------------------------------------------------------------
    # Async send helpers
    # ------------------------------------------------------------------

    async def _async_send(self, text: str) -> bool:
        """Core async send — returns True on success, False on failure."""
        if self._bot is None:
            logger.error("Cannot send message: bot is not initialised")
            return False

        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            return True
        except Exception as exc:
            logger.error("Failed to send Telegram message: %s", exc, exc_info=True)
            return False

    def _schedule_send(self, text: str) -> None:
        """Schedule a send from any thread (thread-safe)."""
        if not self._running or self._loop is None:
            logger.warning("TelegramAlertBot not running — message dropped")
            return
        asyncio.run_coroutine_threadsafe(self._async_send(text), self._loop)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt_price(value: Any) -> str:
        """Format a numeric value as a ₹ price string."""
        try:
            return f"₹{float(value):,.2f}"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _fmt_pct(value: Any) -> str:
        """Format a numeric value as a percentage string."""
        try:
            return f"{float(value):.1f}%"
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _sep() -> str:
        return "━━━━━━━━━━━━━━"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_trade_open(self, trade: dict) -> None:
        """Send a formatted trade-entry alert.

        Expected *trade* keys (lenient — missing keys show 'N/A'):
            symbol, direction, option_type, strike, entry_price, sl,
            target, strategy, confidence, capital_remaining
        """
        try:
            direction = str(trade.get("direction", "N/A")).upper()
            emoji = "🟢" if direction == "BUY" else "🔴"
            strike = trade.get("strike", "N/A")
            option_type = str(trade.get("option_type", "")).upper()
            symbol = str(trade.get("symbol", "N/A")).upper()
            label = f"{symbol} {strike} {option_type}".strip()

            text = (
                f"{emoji} <b>TRADE OPENED</b>\n"
                f"{self._sep()}\n"
                f"📊 <b>{label}</b>\n"
                f"📂 Direction: {direction}\n"
                f"💰 Entry: {self._fmt_price(trade.get('entry_price'))}\n"
                f"🛑 SL: {self._fmt_price(trade.get('sl'))}\n"
                f"🎯 Target: {self._fmt_price(trade.get('target'))}\n"
                f"🤖 Strategy: {trade.get('strategy', 'N/A')}\n"
                f"📈 Confidence: {self._fmt_pct(trade.get('confidence'))}\n"
                f"💵 Capital: {self._fmt_price(trade.get('capital_remaining'))}\n"
                f"{self._sep()}"
            )
            self._schedule_send(text)
            logger.info("Trade open alert queued: %s", label)
        except Exception as exc:
            logger.error("Error formatting trade open alert: %s", exc, exc_info=True)

    def send_trade_close(self, trade: dict, pnl: float) -> None:
        """Send a trade-exit alert.

        Args:
            trade: Trade dict (expects exit_price, symbol, strike, option_type,
                   exit_reason, and optionally direction).
            pnl: Profit/loss amount for this trade.
        """
        try:
            pnl_total = trade.get("total_pnl", pnl)
            is_win = pnl >= 0
            emoji = "✅" if is_win else "❌"
            result = "PROFIT" if is_win else "LOSS"

            strike = trade.get("strike", "N/A")
            option_type = str(trade.get("option_type", "")).upper()
            symbol = str(trade.get("symbol", "N/A")).upper()
            label = f"{symbol} {strike} {option_type}".strip()

            pnl_sign = "+" if pnl >= 0 else ""
            total_sign = "+" if pnl_total >= 0 else ""

            text = (
                f"{emoji} <b>TRADE CLOSED</b>\n"
                f"{self._sep()}\n"
                f"📊 <b>{label}</b>\n"
                f"💰 Exit: {self._fmt_price(trade.get('exit_price'))}\n"
                f"💵 P&L: {pnl_sign}{self._fmt_price(pnl)}\n"
                f"📊 Total P&L: {total_sign}{self._fmt_price(pnl_total)}\n"
                f"🏷 Result: <b>{result}</b>\n"
                f"📝 Reason: {trade.get('exit_reason', 'N/A')}\n"
                f"{self._sep()}"
            )
            self._schedule_send(text)
            logger.info("Trade close alert queued: %s | PnL %s", label, pnl)
        except Exception as exc:
            logger.error("Error formatting trade close alert: %s", exc, exc_info=True)

    def send_daily_report(self, report: dict) -> None:
        """Send an end-of-day summary report.

        Expected *report* keys (lenient):
            total_trades, wins, losses, net_pnl, capital, date
        """
        try:
            net_pnl = report.get("net_pnl", 0)
            sign = "+" if net_pnl >= 0 else ""
            win_rate = 0
            total = report.get("total_trades", 0)
            if total > 0:
                win_rate = (report.get("wins", 0) / total) * 100

            text = (
                f"📋 <b>DAILY REPORT</b>\n"
                f"{self._sep()}\n"
                f"📅 Date: {report.get('date', datetime.now().strftime('%Y-%m-%d'))}\n"
                f"📊 Total Trades: {total}\n"
                f"✅ Wins: {report.get('wins', 0)}\n"
                f"❌ Losses: {report.get('losses', 0)}\n"
                f"📈 Win Rate: {win_rate:.1f}%\n"
                f"💵 Net P&L: <b>{sign}{self._fmt_price(net_pnl)}</b>\n"
                f"🏦 Capital: {self._fmt_price(report.get('capital'))}\n"
                f"{self._sep()}\n"
                f"⏰ Generated at {datetime.now().strftime('%H:%M:%S')}\n"
            )
            self._schedule_send(text)
            logger.info("Daily report queued: %s trades, net %s", total, net_pnl)
        except Exception as exc:
            logger.error("Error formatting daily report: %s", exc, exc_info=True)

    def send_alert(self, message: str) -> None:
        """Send a generic alert / information message."""
        try:
            text = (
                f"📢 <b>ALERT</b>\n"
                f"{self._sep()}\n"
                f"{message}\n"
                f"{self._sep()}"
            )
            self._schedule_send(text)
            logger.info("Generic alert queued")
        except Exception as exc:
            logger.error("Error formatting alert: %s", exc, exc_info=True)

    def send_error(self, error_message: str) -> None:
        """Send an error alert."""
        try:
            text = (
                f"⚠️ <b>ERROR</b>\n"
                f"{self._sep()}\n"
                f"🔥 {error_message}\n"
                f"{self._sep()}"
            )
            self._schedule_send(text)
            logger.info("Error alert queued: %s", error_message)
        except Exception as exc:
            logger.error("Error formatting error alert: %s", exc, exc_info=True)
