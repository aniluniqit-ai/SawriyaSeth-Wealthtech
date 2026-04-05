"""
session_manager.py - Session Management for Broker and Telegram

JSS Sawriya Seth Wealthtech
Handles persistence of Kotak Neo API sessions and Telegram bot sessions.
Provides safe file I/O with graceful error handling for missing files,
corrupt data, and permission issues.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants – resolved relative to the project root (two levels up)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_SESSIONS_DIR = _DATA_DIR / "sessions"
_KOTAK_SESSION_PATH = _SESSIONS_DIR / "kotak_session.json"
_TG_SESSION_DIR = _DATA_DIR / "telegram"


# =========================================================================
# Kotak Neo Session Helpers
# =========================================================================

def _ensure_sessions_dir() -> None:
    """Create the sessions directory tree if it does not already exist."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug("Sessions directory ensured at: %s", _SESSIONS_DIR)


def save_kotak_session(data: dict[str, Any]) -> str:
    """Persist Kotak Neo session data to *data/sessions/kotak_session.json*.

    The *data* dict is augmented with a ``saved_at`` ISO-8601 timestamp before
    being written so callers can determine freshness on load.

    Args:
        data: Arbitrary session payload returned by the Kotak Neo login flow
              (typically includes ``sid``, ``token``, ``userId``, etc.).

    Returns:
        Absolute path to the written JSON file.

    Raises:
        OSError / IOError: If the file cannot be written (permissions, disk
        full, etc.).  The caller should catch and handle appropriately.
    """
    _ensure_sessions_dir()

    # Stamp with save time for staleness checks
    data["saved_at"] = datetime.now().isoformat()

    try:
        with open(_KOTAK_SESSION_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info(
            "Kotak session saved to %s (saved_at=%s)",
            _KOTAK_SESSION_PATH,
            data["saved_at"],
        )
    except (OSError, IOError) as exc:
        logger.error("Failed to save Kotak session: %s", exc, exc_info=True)
        raise

    return str(_KOTAK_SESSION_PATH)


def load_kotak_session() -> dict[str, Any] | None:
    """Load previously saved Kotak Neo session from disk.

    Returns:
        The deserialized session dict if the file exists and contains valid
        JSON, or ``None`` if the file is missing or corrupt.

    Side-effects:
        Logs a warning on any failure so operators can inspect.
    """
    _ensure_sessions_dir()

    if not _KOTAK_SESSION_PATH.exists():
        logger.warning("Kotak session file not found: %s", _KOTAK_SESSION_PATH)
        return None

    try:
        with open(_KOTAK_SESSION_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, dict):
            logger.warning(
                "Kotak session file contains non-dict data; ignoring."
            )
            return None

        logger.info("Kotak session loaded from %s", _KOTAK_SESSION_PATH)
        return data

    except json.JSONDecodeError as exc:
        logger.error(
            "Kotak session file is corrupt (%s); returning None.", exc
        )
        return None
    except (OSError, IOError) as exc:
        logger.error("Failed to read Kotak session: %s", exc, exc_info=True)
        return None


# =========================================================================
# Telegram Session Helpers
# =========================================================================

def _ensure_tg_dir() -> None:
    """Create the Telegram data directory if it does not already exist."""
    _TG_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    logger.debug("Telegram data directory ensured at: %s", _TG_SESSION_DIR)


def save_tg_session_file(session_name: str = "jss_bot") -> str:
    """Mark that a Telegram session file exists.

    Telethon manages its own ``.session`` SQLite files.  This helper creates
    a small sentinel JSON file (*data/telegram/<name>.session.marker*) that
    records the creation timestamp, which the platform can check via
    :func:`has_tg_session`.

    Args:
        session_name: Name of the Telethon session (default ``"jss_bot"``).

    Returns:
        Path to the sentinel marker file as a string.
    """
    _ensure_tg_dir()

    marker_path = _TG_SESSION_DIR / f"{session_name}.session.marker"
    marker_data = {
        "session_name": session_name,
        "created_at": datetime.now().isoformat(),
    }

    try:
        with open(marker_path, "w", encoding="utf-8") as fh:
            json.dump(marker_data, fh, indent=2)
        logger.info("Telegram session marker saved to %s", marker_path)
    except (OSError, IOError) as exc:
        logger.error("Failed to save Telegram session marker: %s", exc)
        raise

    return str(marker_path)


def has_tg_session(session_name: str = "jss_bot") -> bool:
    """Check whether a Telegram session marker file exists.

    This does **not** validate the underlying Telethon ``.session`` file
    itself – it merely indicates that a session has been created at least
    once.  If the Telethon session file was manually deleted, this marker
    could be stale.

    Args:
        session_name: Name of the Telethon session to check.

    Returns:
        ``True`` if the marker file exists, ``False`` otherwise.
    """
    marker_path = _TG_SESSION_DIR / f"{session_name}.session.marker"
    exists = marker_path.exists()
    logger.debug(
        "Telegram session check for '%s': %s", session_name, exists
    )
    return exists
