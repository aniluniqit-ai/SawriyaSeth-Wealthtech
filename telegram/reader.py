"""
reader.py - Telegram Group Reader for JSS Sawriya Seth Wealthtech

Reads messages from trading signal groups using Telethon (MTProto).
Runs synchronously inside a background thread and dispatches callbacks
to registered message handlers.

First run requires interactive OTP entry — logged to the console.
"""

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Type alias for the user-facing callback signature
MessageCallback = Callable[[str, str, str], None]


class TelegramReader:
    """Read messages from Telegram trading groups.

    Uses Telethon in synchronous mode inside a daemon thread so the main
    application is never blocked.

    Args:
        api_id: Telegram API ID (from my.telegram.org).
        api_hash: Telegram API hash.
        phone: Phone number in international format (e.g. "+919876543210").
        session_name: Telethon session name (default ``"jss_reader"``).
    """

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str,
        session_name: str = "jss_reader",
    ) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._session_name = session_name

        self._client: Any = None  # Telethon TelegramClient (lazy import)
        self._thread: threading.Thread | None = None
        self._running = False
        self._callbacks: list[MessageCallback] = []
        self._groups_to_watch: list[str] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session helpers (delegates to brokers.session_manager)
    # ------------------------------------------------------------------

    def _save_session(self) -> None:
        """Mark the current session as saved via brokers.session_manager."""
        try:
            from brokers.session_manager import save_tg_session_file
            save_tg_session_file(self._session_name)
            logger.info("Session marker saved for '%s'", self._session_name)
        except Exception as exc:
            logger.error("Failed to save session marker: %s", exc, exc_info=True)

    def _load_session(self) -> bool:
        """Check whether a session already exists.

        Returns:
            ``True`` if a session marker is found, ``False`` otherwise.
        """
        try:
            from brokers.session_manager import has_tg_session
            exists = has_tg_session(self._session_name)
            if exists:
                logger.info("Existing session found for '%s'", self._session_name)
            else:
                logger.info("No existing session for '%s' — OTP will be required", self._session_name)
            return exists
        except Exception as exc:
            logger.error("Failed to check session: %s", exc, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, groups_to_watch: list[str]) -> None:
        """Start the reader in a background thread.

        On the very first run the user must interactively enter the OTP code
        in the console.  Subsequent runs will reuse the saved session.

        Args:
            groups_to_watch: List of group usernames or titles to monitor.
        """
        if self._running:
            logger.warning("TelegramReader is already running")
            return

        self._groups_to_watch = list(groups_to_watch)
        self._running = True

        self._thread = threading.Thread(
            target=self._run,
            name="tg-reader",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "TelegramReader started (watching %d groups)", len(groups_to_watch)
        )

    def _run(self) -> None:
        """Main loop — lives inside the daemon thread."""
        try:
            from telethon import TelegramClient
            from telethon.errors import SessionPasswordNeededError
        except ImportError:
            logger.error(
                "Telethon is not installed. Install it with: pip install telethon"
            )
            self._running = False
            return

        session_path = f"data/telegram/{self._session_name}"
        client = TelegramClient(session_path, self._api_id, self._api_hash)
        self._client = client

        try:
            logger.info("Connecting to Telegram...")
            client.connect()

            if not client.is_user_authorized():
                has_session = self._load_session()
                if not has_session:
                    logger.info(
                        "⚠️  No session found. Sending OTP to %s ...", self._phone
                    )
                    logger.info(
                        "👉 Check your Telegram app for the OTP code and enter it in the console."
                    )

                client.send_code_request(self._phone)
                try:
                    code = input("Enter the OTP code you received: ").strip()
                    client.sign_in(self._phone, code)
                except SessionPasswordNeededError:
                    password = input("Two-factor password required: ").strip()
                    client.sign_in(password=password)

                # First successful auth — save session marker
                self._save_session()
                logger.info("✅ Successfully authenticated with Telegram")
            else:
                logger.info("✅ Reusing existing Telegram session")

            me = client.get_me()
            logger.info("Logged in as: %s (ID: %s)", me.first_name, me.id)

            # Resolve group entities once
            group_entities = []
            for group_name in self._groups_to_watch:
                try:
                    entity = client.get_entity(group_name)
                    group_entities.append((group_name, entity))
                    logger.info("Watching group: %s", group_name)
                except Exception as exc:
                    logger.warning(
                        "Could not resolve group '%s': %s", group_name, exc
                    )

            if not group_entities:
                logger.warning("No groups resolved — reader will idle")
                self._running = False
                return

            # --- Event loop: poll for new messages ---------------------------
            logger.info("Reader is now listening for new messages...")
            last_ids: dict[str, int] = {}

            # Get initial message IDs so we don't re-process old ones
            for group_name, entity in group_entities:
                try:
                    messages = client.get_messages(entity, limit=1)
                    if messages:
                        last_ids[group_name] = messages[0].id
                except Exception as exc:
                    logger.warning("Could not fetch last message ID for '%s': %s", group_name, exc)

            # Polling loop — 2-second interval
            while self._running:
                for group_name, entity in group_entities:
                    try:
                        messages = client.get_messages(entity, limit=10, min_id=last_ids.get(group_name, 0))
                        if not messages:
                            continue

                        # Telethon returns newest-first; reverse for chronological order
                        for msg in reversed(messages):
                            if msg.id <= last_ids.get(group_name, 0):
                                continue
                            last_ids[group_name] = max(last_ids.get(group_name, 0), msg.id)

                            sender_name = "Unknown"
                            try:
                                if msg.sender:
                                    sender_name = (
                                        getattr(msg.sender, "first_name", None)
                                        or getattr(msg.sender, "title", None)
                                        or str(msg.sender_id)
                                    )
                            except Exception:
                                sender_name = str(msg.sender_id)

                            message_text = msg.text or ""
                            if not message_text.strip():
                                continue

                            # Dispatch to registered callbacks
                            self._dispatch(group_name, message_text, sender_name)

                    except Exception as exc:
                        logger.error(
                            "Error fetching messages from '%s': %s",
                            group_name,
                            exc,
                            exc_info=True,
                        )

                time.sleep(2)

        except Exception as exc:
            logger.error("TelegramReader crashed: %s", exc, exc_info=True)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
            self._running = False
            logger.info("TelegramReader disconnected")

    def stop(self) -> None:
        """Gracefully stop the reader and join the background thread."""
        if not self._running:
            return

        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("TelegramReader stopped")

    # ------------------------------------------------------------------
    # Callback management
    # ------------------------------------------------------------------

    def on_message(self, callback: MessageCallback) -> None:
        """Register a callback for new messages.

        The callback receives three arguments:
            ``(group_name: str, message_text: str, sender: str)``
        """
        with self._lock:
            self._callbacks.append(callback)
        logger.info("Message callback registered (total: %d)", len(self._callbacks))

    def _dispatch(self, group_name: str, message_text: str, sender: str) -> None:
        """Fan-out a message to all registered callbacks (thread-safe)."""
        with self._lock:
            callbacks = list(self._callbacks)
        for cb in callbacks:
            try:
                cb(group_name, message_text, sender)
            except Exception as exc:
                logger.error(
                    "Message callback error: %s", exc, exc_info=True
                )

    # ------------------------------------------------------------------
    # Utility: fetch recent messages
    # ------------------------------------------------------------------

    def get_recent_messages(self, group: str, limit: int = 20) -> list[dict[str, Any]]:
        """Fetch recent messages from a group.

        This method blocks the calling thread while it fetches messages.
        The reader does **not** need to be running for this to work, but
        the client must have been authenticated at least once.

        Args:
            group: Group username, title, or invite link.
            limit: Maximum number of messages to return (default 20).

        Returns:
            List of dicts with keys: ``id``, ``text``, ``sender``,
            ``timestamp`` (ISO string).
        """
        try:
            from telethon import TelegramClient
        except ImportError:
            logger.error("Telethon is not installed")
            return []

        session_path = f"data/telegram/{self._session_name}"
        client = TelegramClient(session_path, self._api_id, self._api_hash)

        try:
            client.connect()
            if not client.is_user_authorized():
                logger.warning("Cannot fetch messages — not authenticated")
                return []

            entity = client.get_entity(group)
            messages = client.get_messages(entity, limit=limit)

            result: list[dict[str, Any]] = []
            for msg in reversed(messages):
                sender_name = "Unknown"
                try:
                    if msg.sender:
                        sender_name = (
                            getattr(msg.sender, "first_name", None)
                            or getattr(msg.sender, "title", None)
                            or str(msg.sender_id)
                        )
                except Exception:
                    sender_name = str(msg.sender_id)

                result.append(
                    {
                        "id": msg.id,
                        "text": msg.text or "",
                        "sender": sender_name,
                        "timestamp": msg.date.isoformat() if msg.date else "",
                    }
                )

            return result

        except Exception as exc:
            logger.error(
                "Failed to fetch recent messages from '%s': %s",
                group,
                exc,
                exc_info=True,
            )
            return []
        finally:
            try:
                client.disconnect()
            except Exception:
                pass
