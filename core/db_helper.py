"""
db_helper.py - SQLite Database Helper

JSS Sawriya Seth Wealthtech
Persistent storage layer for trades, capital state, market snapshots,
candles, daily reports, system logs, application config, and telegram
messages.  All public methods are thread-safe via ``threading.Lock``.

Author: JSS Sawriya Seth Wealthtech Engineering
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Database:
    """Thread-safe SQLite persistence layer.

    Creates the database file and all required tables on first
    instantiation.  Every write operation acquires a lock so the
    database can be safely accessed from multiple threads (e.g. the
    trading engine, market-data thread, and telegram listener).

    Args:
        db_path: Path to the SQLite database file (default ``data/jss_trading.db``).
    """

    # ------------------------------------------------------------------
    # Schema definitions
    # ------------------------------------------------------------------

    _SCHEMA: dict[str, str] = {
        "capital": """
            CREATE TABLE IF NOT EXISTS capital (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                initial         REAL NOT NULL DEFAULT 1000.0,
                current         REAL NOT NULL DEFAULT 1000.0,
                peak            REAL NOT NULL DEFAULT 1000.0,
                total_pnl       REAL NOT NULL DEFAULT 0.0,
                wins            INTEGER NOT NULL DEFAULT 0,
                losses          INTEGER NOT NULL DEFAULT 0,
                total_trades    INTEGER NOT NULL DEFAULT 0,
                today_pnl       REAL NOT NULL DEFAULT 0.0,
                today_trades    INTEGER NOT NULL DEFAULT 0,
                today_wins      INTEGER NOT NULL DEFAULT 0,
                today_losses    INTEGER NOT NULL DEFAULT 0,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "trades": """
            CREATE TABLE IF NOT EXISTS trades (
                id              TEXT PRIMARY KEY,
                symbol          TEXT NOT NULL,
                direction       TEXT NOT NULL,
                option_type     TEXT NOT NULL,
                strike          INTEGER NOT NULL,
                entry_price     REAL NOT NULL,
                exit_price      REAL,
                entry_time      TEXT NOT NULL,
                exit_time       TEXT,
                qty             INTEGER NOT NULL,
                lot_size        INTEGER NOT NULL DEFAULT 1,
                sl              REAL NOT NULL DEFAULT 0.0,
                target          REAL NOT NULL DEFAULT 0.0,
                trailing_sl     REAL NOT NULL DEFAULT 0.0,
                pnl             REAL NOT NULL DEFAULT 0.0,
                status          TEXT NOT NULL DEFAULT 'OPEN',
                strategy        TEXT NOT NULL DEFAULT '',
                confidence      REAL NOT NULL DEFAULT 0.0,
                reason          TEXT NOT NULL DEFAULT '',
                exit_reason     TEXT NOT NULL DEFAULT '',
                capital         REAL NOT NULL DEFAULT 1000.0,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "market_snapshots": """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                ltp             REAL NOT NULL,
                change_pct      REAL NOT NULL DEFAULT 0.0,
                high            REAL NOT NULL DEFAULT 0.0,
                low             REAL NOT NULL DEFAULT 0.0,
                open            REAL NOT NULL DEFAULT 0.0,
                close           REAL NOT NULL DEFAULT 0.0,
                volume          INTEGER NOT NULL DEFAULT 0,
                oi_ce           INTEGER NOT NULL DEFAULT 0,
                oi_pe           INTEGER NOT NULL DEFAULT 0,
                iv_ce           REAL NOT NULL DEFAULT 0.0,
                iv_pe           REAL NOT NULL DEFAULT 0.0,
                atm_ce_premium  REAL NOT NULL DEFAULT 0.0,
                atm_pe_premium  REAL NOT NULL DEFAULT 0.0,
                timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "candles": """
            CREATE TABLE IF NOT EXISTS candles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol          TEXT NOT NULL,
                interval        TEXT NOT NULL,
                timestamp       REAL NOT NULL,
                open            REAL NOT NULL,
                high            REAL NOT NULL,
                low             REAL NOT NULL,
                close           REAL NOT NULL,
                volume          INTEGER NOT NULL DEFAULT 0,
                UNIQUE(symbol, interval, timestamp)
            );
        """,
        "daily_reports": """
            CREATE TABLE IF NOT EXISTS daily_reports (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL UNIQUE,
                total_pnl       REAL NOT NULL DEFAULT 0.0,
                total_trades    INTEGER NOT NULL DEFAULT 0,
                wins            INTEGER NOT NULL DEFAULT 0,
                losses          INTEGER NOT NULL DEFAULT 0,
                win_rate        REAL NOT NULL DEFAULT 0.0,
                avg_win         REAL NOT NULL DEFAULT 0.0,
                avg_loss        REAL NOT NULL DEFAULT 0.0,
                max_win         REAL NOT NULL DEFAULT 0.0,
                max_loss        REAL NOT NULL DEFAULT 0.0,
                best_strategy   TEXT NOT NULL DEFAULT '',
                capital_start   REAL NOT NULL DEFAULT 0.0,
                capital_end     REAL NOT NULL DEFAULT 0.0,
                report_data     TEXT NOT NULL DEFAULT '{}',
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "system_logs": """
            CREATE TABLE IF NOT EXISTS system_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                level           TEXT NOT NULL DEFAULT 'INFO',
                message         TEXT NOT NULL,
                source          TEXT NOT NULL DEFAULT 'SYSTEM',
                metadata        TEXT NOT NULL DEFAULT '{}',
                timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "app_config": """
            CREATE TABLE IF NOT EXISTS app_config (
                key             TEXT PRIMARY KEY,
                value           TEXT NOT NULL,
                updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
        "telegram_messages": """
            CREATE TABLE IF NOT EXISTS telegram_messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id      INTEGER NOT NULL DEFAULT 0,
                chat_id         INTEGER NOT NULL DEFAULT 0,
                direction       TEXT NOT NULL DEFAULT 'INCOMING',
                text            TEXT NOT NULL DEFAULT '',
                sender_id       INTEGER NOT NULL DEFAULT 0,
                sender_name     TEXT NOT NULL DEFAULT '',
                timestamp       TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """,
    }

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def __init__(self, db_path: str = "data/jss_trading.db") -> None:
        self._db_path: str = db_path

        # Ensure parent directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn: sqlite3.Connection = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()

        self._create_tables()
        logger.info("Database initialised at %s", os.path.abspath(db_path))

    def _create_tables(self) -> None:
        """Create all tables using ``CREATE TABLE IF NOT EXISTS``."""
        with self._lock:
            for name, ddl in self._SCHEMA.items():
                try:
                    self._conn.execute(ddl)
                    logger.debug("Ensured table '%s' exists.", name)
                except sqlite3.Error as exc:
                    logger.error("Failed to create table '%s': %s", name, exc)
            self._conn.commit()

    # ------------------------------------------------------------------
    # Trade operations
    # ------------------------------------------------------------------

    def save_trade(self, trade_dict: dict[str, Any]) -> bool:
        """Insert or update a trade record.

        If a trade with the same ``id`` already exists it will be updated
        (upsert).  All keys from the shared trade-dict structure are stored.

        Args:
            trade_dict: Full trade dictionary.

        Returns:
            ``True`` on success, ``False`` on failure.
        """
        sql = """
            INSERT INTO trades (
                id, symbol, direction, option_type, strike, entry_price, exit_price,
                entry_time, exit_time, qty, lot_size, sl, target, trailing_sl,
                pnl, status, strategy, confidence, reason, exit_reason, capital
            ) VALUES (
                :id, :symbol, :direction, :option_type, :strike, :entry_price,
                :exit_price, :entry_time, :exit_time, :qty, :lot_size,
                :sl, :target, :trailing_sl, :pnl, :status, :strategy,
                :confidence, :reason, :exit_reason, :capital
            )
            ON CONFLICT(id) DO UPDATE SET
                symbol        = excluded.symbol,
                direction     = excluded.direction,
                option_type   = excluded.option_type,
                strike        = excluded.strike,
                entry_price   = excluded.entry_price,
                exit_price    = COALESCE(excluded.exit_price, trades.exit_price),
                exit_time     = COALESCE(excluded.exit_time, trades.exit_time),
                qty           = excluded.qty,
                lot_size      = excluded.lot_size,
                sl            = excluded.sl,
                target        = excluded.target,
                trailing_sl   = excluded.trailing_sl,
                pnl           = excluded.pnl,
                status        = excluded.status,
                strategy      = excluded.strategy,
                confidence    = excluded.confidence,
                reason        = excluded.reason,
                exit_reason   = COALESCE(excluded.exit_reason, trades.exit_reason),
                capital       = excluded.capital,
                updated_at    = datetime('now')
        """
        try:
            with self._lock:
                self._conn.execute(sql, trade_dict)
                self._conn.commit()
            logger.info("Trade saved: %s (%s)", trade_dict.get("id"), trade_dict.get("status"))
            return True
        except sqlite3.Error as exc:
            logger.error("save_trade failed for %s: %s", trade_dict.get("id"), exc)
            return False

    def get_open_trades(self) -> list[dict[str, Any]]:
        """Return all trades with status ``OPEN``.

        Returns:
            List of trade dicts.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC"
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("get_open_trades failed: %s", exc)
            return []

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
    ) -> Optional[dict[str, Any]]:
        """Mark a trade as CLOSED and calculate P&L.

        P&L is computed as::

            BUY  → (exit_price - entry_price) * qty
            SELL → (entry_price - exit_price) * qty

        Args:
            trade_id:    The trade ``id``.
            exit_price:  Price at which the trade was closed.
            exit_reason: Reason for exit (``"SL_HIT"``, ``"TARGET"``, etc.).

        Returns:
            Updated trade dict, or ``None`` on failure.
        """
        try:
            with self._lock:
                # Fetch the open trade
                cursor = self._conn.execute(
                    "SELECT * FROM trades WHERE id = ? AND status = 'OPEN'",
                    (trade_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    logger.warning("close_trade: trade %s not found or not OPEN", trade_id)
                    return None

                trade = dict(row)
                direction = trade["direction"]
                entry_price = trade["entry_price"]
                qty = trade["qty"]

                # Calculate P&L
                if direction.upper() == "BUY":
                    pnl = (exit_price - entry_price) * qty
                else:
                    pnl = (entry_price - exit_price) * qty

                pnl = round(pnl, 2)

                now = datetime.now().isoformat()
                self._conn.execute(
                    """
                    UPDATE trades SET
                        exit_price  = ?,
                        exit_time   = ?,
                        pnl         = ?,
                        status      = 'CLOSED',
                        exit_reason = ?,
                        updated_at  = ?
                    WHERE id = ?
                    """,
                    (exit_price, now, pnl, exit_reason, now, trade_id),
                )
                self._conn.commit()

                # Return the updated trade
                trade.update({
                    "exit_price": exit_price,
                    "exit_time": now,
                    "pnl": pnl,
                    "status": "CLOSED",
                    "exit_reason": exit_reason,
                    "updated_at": now,
                })

                logger.info(
                    "Trade %s CLOSED: PnL=%.2f (%s)", trade_id, pnl, exit_reason
                )
                return trade

        except sqlite3.Error as exc:
            logger.error("close_trade failed for %s: %s", trade_id, exc)
            return None

    def get_trade_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent *closed* trades.

        Args:
            limit: Max number of trades to return.

        Returns:
            List of trade dicts ordered by ``exit_time`` descending.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(
                    """
                    SELECT * FROM trades
                    WHERE status = 'CLOSED'
                    ORDER BY exit_time DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("get_trade_history failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Candle operations
    # ------------------------------------------------------------------

    def save_candle(
        self, symbol: str, interval: str, candle_dict: dict[str, Any]
    ) -> bool:
        """Upsert a single candle record.

        The composite unique key ``(symbol, interval, timestamp)`` ensures
        that a duplicate candle for the same period is updated in-place.

        Args:
            symbol:      Underlying symbol (e.g. ``"NIFTY"``).
            interval:    Candle timeframe (e.g. ``"5m"``).
            candle_dict: Dict with keys ``timestamp``, ``open``, ``high``,
                         ``low``, ``close``, ``volume``.

        Returns:
            ``True`` on success.
        """
        ts = candle_dict.get("timestamp", 0)
        # Normalise timestamp to a numeric value
        if isinstance(ts, datetime):
            ts = ts.timestamp()
        ts = float(ts)

        sql = """
            INSERT INTO candles (symbol, interval, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, timestamp) DO UPDATE SET
                open    = excluded.open,
                high    = excluded.high,
                low     = excluded.low,
                close   = excluded.close,
                volume  = excluded.volume
        """
        try:
            with self._lock:
                self._conn.execute(
                    sql,
                    (
                        symbol.upper(),
                        interval,
                        ts,
                        candle_dict.get("open", 0),
                        candle_dict.get("high", 0),
                        candle_dict.get("low", 0),
                        candle_dict.get("close", 0),
                        candle_dict.get("volume", 0),
                    ),
                )
                self._conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("save_candle failed: %s", exc)
            return False

    def save_candles_bulk(
        self, symbol: str, interval: str, candles: list[dict[str, Any]]
    ) -> int:
        """Bulk upsert candles for a symbol/interval pair.

        Args:
            symbol:   Underlying symbol.
            interval: Candle timeframe.
            candles:  List of candle dicts.

        Returns:
            Number of candles successfully upserted.
        """
        sql = """
            INSERT INTO candles (symbol, interval, timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, timestamp) DO UPDATE SET
                open    = excluded.open,
                high    = excluded.high,
                low     = excluded.low,
                close   = excluded.close,
                volume  = excluded.volume
        """
        rows: list[tuple[Any, ...]] = []
        for c in candles:
            ts = c.get("timestamp", 0)
            if isinstance(ts, datetime):
                ts = ts.timestamp()
            rows.append((
                symbol.upper(), interval, float(ts),
                c.get("open", 0), c.get("high", 0), c.get("low", 0),
                c.get("close", 0), c.get("volume", 0),
            ))

        try:
            with self._lock:
                self._conn.executemany(sql, rows)
                self._conn.commit()
            logger.info("Bulk upserted %d candles for %s (%s)", len(rows), symbol, interval)
            return len(rows)
        except sqlite3.Error as exc:
            logger.error("save_candles_bulk failed: %s", exc)
            return 0

    def get_candles(
        self, symbol: str, interval: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch historical candles ordered by timestamp ascending.

        Args:
            symbol:   Underlying symbol.
            interval: Candle timeframe.
            limit:    Max number of candles (default 100).

        Returns:
            List of candle dicts.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(
                    """
                    SELECT timestamp, open, high, low, close, volume
                    FROM candles
                    WHERE symbol = ? AND interval = ?
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (symbol.upper(), interval, limit),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("get_candles failed for %s/%s: %s", symbol, interval, exc)
            return []

    # ------------------------------------------------------------------
    # Market snapshots
    # ------------------------------------------------------------------

    def save_market_snapshot(self, data_dict: dict[str, Any]) -> bool:
        """Save a real-time market snapshot (LTP, OI, IV, etc.).

        Args:
            data_dict: Market data dict.  Expected keys include ``symbol``,
                       ``ltp``, ``change_pct``, ``high``, ``low``, ``open``,
                       ``close``, ``volume``, ``oi_ce``, ``oi_pe``, ``iv_ce``,
                       ``iv_pe``, ``atm_ce_premium``, ``atm_pe_premium``.

        Returns:
            ``True`` on success.
        """
        sql = """
            INSERT INTO market_snapshots (
                symbol, ltp, change_pct, high, low, open, close, volume,
                oi_ce, oi_pe, iv_ce, iv_pe, atm_ce_premium, atm_pe_premium
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._lock:
                self._conn.execute(
                    sql,
                    (
                        data_dict.get("symbol", "").upper(),
                        data_dict.get("ltp", 0),
                        data_dict.get("change_pct", 0),
                        data_dict.get("high", 0),
                        data_dict.get("low", 0),
                        data_dict.get("open", 0),
                        data_dict.get("close", 0),
                        data_dict.get("volume", 0),
                        data_dict.get("oi_ce", 0),
                        data_dict.get("oi_pe", 0),
                        data_dict.get("iv_ce", 0),
                        data_dict.get("iv_pe", 0),
                        data_dict.get("atm_ce_premium", 0),
                        data_dict.get("atm_pe_premium", 0),
                    ),
                )
                self._conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("save_market_snapshot failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Capital operations
    # ------------------------------------------------------------------

    def get_capital_state(self) -> Optional[dict[str, Any]]:
        """Return the current capital row (single-row table).

        Returns:
            Capital state dict, or ``None`` if no row exists.
        """
        try:
            with self._lock:
                cursor = self._conn.execute("SELECT * FROM capital ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
        except sqlite3.Error as exc:
            logger.error("get_capital_state failed: %s", exc)
            return None

    def update_capital(self, current: float, pnl: float = 0.0) -> bool:
        """Update the capital row with a new *current* value and P&L delta.

        The ``peak`` field is bumped whenever *current* exceeds the stored
        peak.  The daily counters are reset at the start of each new day
        (detected by comparing ``updated_at`` to today).

        Args:
            current: New capital amount.
            pnl:     Absolute P&L change for this trade.

        Returns:
            ``True`` on success.
        """
        try:
            with self._lock:
                # Fetch existing state
                cursor = self._conn.execute(
                    "SELECT * FROM capital ORDER BY id DESC LIMIT 1"
                )
                row = cursor.fetchone()

                if row is None:
                    # First time — insert
                    self._conn.execute(
                        """
                        INSERT INTO capital (initial, current, peak, total_pnl,
                            wins, losses, total_trades, today_pnl, today_trades,
                            today_wins, today_losses)
                        VALUES (?, ?, ?, ?, 0, 0, 0, ?, 0, 0, 0)
                        """,
                        (current, current, current, pnl, pnl),
                    )
                    self._conn.commit()
                    logger.info("Capital record created: current=%.2f", current)
                    return True

                state = dict(row)

                # Detect new day → reset daily counters
                updated_at = state.get("updated_at", "")
                today_str = datetime.now().strftime("%Y-%m-%d")
                reset_daily = (
                    not updated_at or today_str not in str(updated_at)[:10]
                )

                today_pnl = state["today_pnl"] + pnl if not reset_daily else pnl
                today_trades = 1 if reset_daily else state["today_trades"] + 1
                today_wins = (1 if pnl > 0 else 0) if reset_daily else (
                    state["today_wins"] + (1 if pnl > 0 else 0)
                )
                today_losses = (1 if pnl < 0 else 0) if reset_daily else (
                    state["today_losses"] + (1 if pnl < 0 else 0)
                )

                new_peak = max(state["peak"], current)
                new_total_pnl = state["total_pnl"] + pnl
                new_wins = state["wins"] + (1 if pnl > 0 else 0)
                new_losses = state["losses"] + (1 if pnl < 0 else 0)
                new_total = state["total_trades"] + 1

                self._conn.execute(
                    """
                    UPDATE capital SET
                        current      = ?,
                        peak         = ?,
                        total_pnl    = ?,
                        wins         = ?,
                        losses       = ?,
                        total_trades = ?,
                        today_pnl    = ?,
                        today_trades = ?,
                        today_wins   = ?,
                        today_losses = ?,
                        updated_at   = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        current, new_peak, new_total_pnl, new_wins, new_losses,
                        new_total, today_pnl, today_trades, today_wins,
                        today_losses, state["id"],
                    ),
                )
                self._conn.commit()
                logger.info(
                    "Capital updated: current=%.2f, total_pnl=%.2f, today_pnl=%.2f",
                    current, new_total_pnl, today_pnl,
                )
                return True

        except sqlite3.Error as exc:
            logger.error("update_capital failed: %s", exc)
            return False

    def reset_daily_counters(self) -> bool:
        """Reset today_* counters to zero (called at start of trading day).

        Returns:
            ``True`` on success.
        """
        try:
            with self._lock:
                self._conn.execute(
                    """
                    UPDATE capital SET
                        today_pnl   = 0,
                        today_trades = 0,
                        today_wins  = 0,
                        today_losses = 0,
                        updated_at  = datetime('now')
                    WHERE id = (SELECT id FROM capital ORDER BY id DESC LIMIT 1)
                    """
                )
                self._conn.commit()
            logger.info("Daily capital counters reset.")
            return True
        except sqlite3.Error as exc:
            logger.error("reset_daily_counters failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Daily reports
    # ------------------------------------------------------------------

    def save_daily_report(self, report_dict: dict[str, Any]) -> bool:
        """Save or merge a daily trading report.

        Uses ``ON CONFLICT(date) DO UPDATE`` so the report for a given
        date is always the latest merged version.

        Args:
            report_dict: Report data dict.  Must contain ``date`` key.

        Returns:
            ``True`` on success.
        """
        report_data_json = json.dumps(report_dict.get("report_data", {}))
        sql = """
            INSERT INTO daily_reports (
                date, total_pnl, total_trades, wins, losses, win_rate,
                avg_win, avg_loss, max_win, max_loss, best_strategy,
                capital_start, capital_end, report_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_pnl     = excluded.total_pnl,
                total_trades  = excluded.total_trades,
                wins          = excluded.wins,
                losses        = excluded.losses,
                win_rate      = excluded.win_rate,
                avg_win       = excluded.avg_win,
                avg_loss      = excluded.avg_loss,
                max_win       = excluded.max_win,
                max_loss      = excluded.max_loss,
                best_strategy = excluded.best_strategy,
                capital_start = excluded.capital_start,
                capital_end   = excluded.capital_end,
                report_data   = excluded.report_data,
                updated_at    = datetime('now')
        """
        try:
            with self._lock:
                self._conn.execute(
                    sql,
                    (
                        report_dict.get("date", datetime.now().strftime("%Y-%m-%d")),
                        report_dict.get("total_pnl", 0),
                        report_dict.get("total_trades", 0),
                        report_dict.get("wins", 0),
                        report_dict.get("losses", 0),
                        report_dict.get("win_rate", 0),
                        report_dict.get("avg_win", 0),
                        report_dict.get("avg_loss", 0),
                        report_dict.get("max_win", 0),
                        report_dict.get("max_loss", 0),
                        report_dict.get("best_strategy", ""),
                        report_dict.get("capital_start", 0),
                        report_dict.get("capital_end", 0),
                        report_data_json,
                    ),
                )
                self._conn.commit()
            logger.info("Daily report saved for %s", report_dict.get("date"))
            return True
        except sqlite3.Error as exc:
            logger.error("save_daily_report failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # System logs
    # ------------------------------------------------------------------

    def log(
        self,
        level: str,
        message: str,
        source: str = "SYSTEM",
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Insert a row into ``system_logs``.

        Also forwards the message to Python's standard ``logging`` module
        at the corresponding level.

        Args:
            level:    Log level string (``DEBUG``, ``INFO``, ``WARNING``,
                      ``ERROR``, ``CRITICAL``).
            message:  Log message.
            source:   Originating component (e.g. ``"ENGINE"``,
                      ``"BROKER"``, ``"RISK"``).
            metadata: Optional dict serialised as JSON.

        Returns:
            ``True`` on success.
        """
        meta_json = json.dumps(metadata or {})

        # Forward to Python logger
        py_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(py_level, "[%s] %s", source, message)

        sql = """
            INSERT INTO system_logs (level, message, source, metadata)
            VALUES (?, ?, ?, ?)
        """
        try:
            with self._lock:
                self._conn.execute(sql, (level.upper(), message, source, meta_json))
                self._conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("log insert failed: %s", exc)
            return False

    def get_logs(
        self,
        limit: int = 100,
        level: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch system logs, optionally filtered by *level*.

        Args:
            limit: Max rows to return.
            level: If provided, only rows matching this level.

        Returns:
            List of log dicts ordered by most recent first.
        """
        try:
            with self._lock:
                if level:
                    cursor = self._conn.execute(
                        """
                        SELECT * FROM system_logs
                        WHERE level = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (level.upper(), limit),
                    )
                else:
                    cursor = self._conn.execute(
                        "SELECT * FROM system_logs ORDER BY id DESC LIMIT ?",
                        (limit,),
                    )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("get_logs failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # App config
    # ------------------------------------------------------------------

    def get_app_config(self, key: str) -> Optional[str]:
        """Get a configuration value by key.

        Args:
            key: Configuration key.

        Returns:
            The value string, or ``None`` if not found.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT value FROM app_config WHERE key = ?", (key,)
                )
                row = cursor.fetchone()
                return row["value"] if row else None
        except sqlite3.Error as exc:
            logger.error("get_app_config failed for key '%s': %s", key, exc)
            return None

    def set_app_config(self, key: str, value: str) -> bool:
        """Set or update a configuration value.

        Args:
            key:   Configuration key.
            value: Value to store (string).

        Returns:
            ``True`` on success.
        """
        sql = """
            INSERT INTO app_config (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                updated_at = datetime('now')
        """
        try:
            with self._lock:
                self._conn.execute(sql, (key, str(value)))
                self._conn.commit()
            logger.debug("Config set: %s = %s", key, value)
            return True
        except sqlite3.Error as exc:
            logger.error("set_app_config failed for key '%s': %s", key, exc)
            return False

    # ------------------------------------------------------------------
    # Telegram messages
    # ------------------------------------------------------------------

    def save_telegram_message(self, msg_dict: dict[str, Any]) -> bool:
        """Persist an incoming or outgoing Telegram message.

        Args:
            msg_dict: Message data. Expected keys: ``message_id``,
                      ``chat_id``, ``direction``, ``text``, ``sender_id``,
                      ``sender_name``.

        Returns:
            ``True`` on success.
        """
        sql = """
            INSERT INTO telegram_messages
                (message_id, chat_id, direction, text, sender_id, sender_name)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            with self._lock:
                self._conn.execute(
                    sql,
                    (
                        msg_dict.get("message_id", 0),
                        msg_dict.get("chat_id", 0),
                        msg_dict.get("direction", "INCOMING"),
                        msg_dict.get("text", ""),
                        msg_dict.get("sender_id", 0),
                        msg_dict.get("sender_name", ""),
                    ),
                )
                self._conn.commit()
            return True
        except sqlite3.Error as exc:
            logger.error("save_telegram_message failed: %s", exc)
            return False

    def get_telegram_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """Fetch recent Telegram messages.

        Args:
            limit: Max rows.

        Returns:
            List of message dicts.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(
                    "SELECT * FROM telegram_messages ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("get_telegram_messages failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def execute_raw(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a raw SQL query and return results as dicts.

        Intended for diagnostics / admin.  Prefer typed methods for
        normal operations.

        Args:
            sql:    SQL statement.
            params: Query parameters.

        Returns:
            List of row dicts.
        """
        try:
            with self._lock:
                cursor = self._conn.execute(sql, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("execute_raw failed: %s – %s", sql, exc)
            return []

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
            logger.info("Database connection closed.")
        except Exception as exc:
            logger.error("Error closing database: %s", exc)
