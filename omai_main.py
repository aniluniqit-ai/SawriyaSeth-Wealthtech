"""
जय श्री सांवरीया सेठ — JSS Sawriya Seth Wealthtech AI Trading
Main Entry Point — Double click/Run this file to start the application

This script:
1. Sets up logging (file + console).
2. Validates the configuration file.
3. Creates the Tkinter root window.
4. Initialises the TradingEngine (brain of the system).
5. Creates the TradingGUI (Tkinter desktop UI).
6. AUTO-STARTS the engine on launch (no button click needed!).
7. Runs the Tkinter main loop.
8. On window close, gracefully stops the engine.
"""

import sys
import os
import logging
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

# Ensure the project root is on sys.path so all imports work
# regardless of where this file is executed from.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ======================================================================
# Logging setup
# ======================================================================

def setup_logging() -> None:
    """Configure application-wide logging to both file and console."""
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "jss_trading.log"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler — DEBUG level, rotating daily
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)

    # Console handler — INFO level, compact format
    console_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    root_logger.addHandler(console_handler)

    logging.info("Logging initialised — file: %s", log_file)


# ======================================================================
# Config check
# ======================================================================

def check_config() -> bool:
    """Verify that ``config/config.json`` exists and is valid JSON.

    If the file is missing, a default configuration is created
    automatically so the user can get started immediately.

    Returns:
        ``True`` if config is usable, ``False`` on hard failure.
    """
    config_path = _PROJECT_ROOT / "config" / "config.json"

    if config_path.exists():
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            logging.info("Config loaded from %s", config_path)
            return True
        except json.JSONDecodeError as exc:
            logging.error("Config JSON parse error: %s", exc)
            return False
        except Exception as exc:
            logging.error("Config read error: %s", exc)
            return False

    # Config missing — create default
    logging.warning(
        "Config file not found at %s — creating default configuration",
        config_path,
    )

    try:
        config_dir = _PROJECT_ROOT / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        default_config = {
            "broker": {
                "client_code": "YOUR_CLIENT_CODE",
                "access_token": "YOUR_ACCESS_TOKEN",
                "mobile": "YOUR_MOBILE",
                "mpin": "YOUR_MPIN",
                "totp_secret": "YOUR_TOTP_SECRET",
            },
            "database": {"path": "data/jss_trading.db"},
            "capital": {
                "initial_capital": 1000.0,
                "max_daily_loss_percent": 5.0,
                "max_open_trades": 3,
                "scale_capital_threshold": 10000.0,
                "lot_multiplier": 50,
            },
            "risk": {
                "sl_percent": 15.0,
                "risk_reward_ratio": 2.0,
                "trailing_sl_activation_pct": 3.0,
                "trailing_sl_trail_pct": 1.5,
                "max_daily_loss_percent": 5.0,
                "strategy_cooldown_minutes": 15,
                "max_consecutive_losses": 3,
            },
            "strategies": {
                "momentum_follow": {"enabled": True, "min_confidence": 65},
                "multi_scalping": {"enabled": True, "min_confidence": 65},
                "reversal_scalp": {"enabled": True, "min_confidence": 65},
                "expiry_heropatla": {"enabled": True, "min_confidence": 65},
            },
            "symbols": ["NIFTY", "BANKNIFTY"],
            "scan_interval_seconds": 3,
            "candle_interval": "1m",
            "candle_limit": 100,
            "square_off_time": "15:15",
            "telegram": {
                "enabled": False,
                "bot_token": "",
                "chat_id": "",
                "reader_enabled": False,
                "api_id": 0,
                "api_hash": "",
                "phone": "",
                "groups_to_watch": [],
            },
            "ai": {
                "enabled": False,
                "api_key": "",
            },
            "daily_report": {
                "enabled": True,
                "export_excel": True,
            },
        }

        import json
        with open(config_path, "w", encoding="utf-8") as fh:
            json.dump(default_config, fh, indent=4)

        logging.info("Default config created at %s", config_path)
        return True

    except Exception as exc:
        logging.error("Failed to create default config: %s", exc)
        return False


# ======================================================================
# Dependency check
# ======================================================================

def check_dependencies() -> bool:
    """Check if all required Python packages are importable.

    Returns:
        ``True`` if all critical dependencies are available.
    """
    critical = [
        ("requests", "HTTP client for broker API"),
        ("pyotp", "TOTP 2FA generation"),
    ]

    optional = [
        ("openpyxl", "Excel report export"),
        ("telegram", "Telegram bot (python-telegram-bot)"),
        ("telethon", "Telegram group reader"),
        ("numpy", "Fast numerical calculations"),
    ]

    missing_critical = []
    missing_optional = []

    for pkg, desc in critical:
        try:
            __import__(pkg)
        except ImportError:
            missing_critical.append(f"{pkg} ({desc})")

    for pkg, desc in optional:
        try:
            __import__(pkg)
        except Exception:
            missing_optional.append(f"{pkg} ({desc})")

    if missing_critical:
        logging.error(
            "CRITICAL packages missing: %s. "
            "Install with: pip install -r requirements.txt",
            ", ".join(missing_critical),
        )
        return False

    if missing_optional:
        logging.warning(
            "Optional packages not installed (some features disabled): %s",
            ", ".join(missing_optional),
        )

    logging.info("All critical dependencies available")
    return True


# ======================================================================
# Main application entry point
# ======================================================================

def main() -> None:
    """Main application entry point.

    This function orchestrates the entire application lifecycle:
    1. Print banner to console.
    2. Setup logging.
    3. Check config.
    4. Check dependencies.
    5. Create Tkinter root window.
    6. Set window properties (title, size, icon).
    7. Create TradingEngine instance.
    8. Create TradingGUI instance.
    9. AUTO-START engine.
    10. Run GUI main loop.
    11. On close: stop engine gracefully.
    """
    # Banner
    print()
    print("  🪷 जय श्री सांवरीया सेठ")
    print("  ─────────────────────────────")
    print("  JSS Sawriya Seth Wealthtech")
    print("  AI Options Trading System")
    print("  ─────────────────────────────")
    print()

    # 1. Setup logging
    setup_logging()
    logging.info("Application starting...")

    # 2. Check config
    if not check_config():
        # Try to show a Tkinter error dialog
        try:
            root_temp = tk.Tk()
            root_temp.withdraw()
            messagebox.showerror(
                "Configuration Error",
                "Could not load or create config/config.json.\n"
                "Please check the logs/ folder for details.",
            )
            root_temp.destroy()
        except Exception:
            pass
        logging.error("Cannot start — config check failed")
        sys.exit(1)

    # 3. Check dependencies
    if not check_dependencies():
        try:
            root_temp = tk.Tk()
            root_temp.withdraw()
            messagebox.showerror(
                "Missing Dependencies",
                "Critical Python packages are missing.\n"
                "Please run: pip install -r requirements.txt\n"
                "Then restart the application.",
            )
            root_temp.destroy()
        except Exception:
            pass
        logging.error("Cannot start — missing dependencies")
        sys.exit(1)

    # 4. Create Tkinter root window
    root = tk.Tk()
    root.title("जय श्री सांवरीया सेठ — JSS Wealthtech AI Trading")
    root.geometry("1400x900")
    root.minsize(1024, 640)

    # Set icon if available
    icon_path = _PROJECT_ROOT / "images" / "app_icon.ico"
    if icon_path.exists():
        try:
            root.iconbitmap(str(icon_path))
        except Exception as exc:
            logging.debug("Could not set window icon: %s", exc)
    else:
        # Try PNG icon fallback
        try:
            from PIL import Image, ImageTk
            png_path = _PROJECT_ROOT / "images" / "app_icon.png"
            if png_path.exists():
                img = Image.open(png_path)
                icon = ImageTk.PhotoImage(img)
                root.iconphoto(True, icon)
        except Exception:
            pass

    # 5. Create TradingEngine instance
    engine = None
    try:
        from core.engine import TradingEngine

        config_path = str(_PROJECT_ROOT / "config" / "config.json")
        engine = TradingEngine(config_path=config_path)
        logging.info("TradingEngine created")
    except Exception as exc:
        logging.error("Failed to create TradingEngine: %s", exc, exc_info=True)
        messagebox.showerror(
            "Engine Error",
            f"Failed to initialise the trading engine:\n{exc}\n\n"
            "Check the logs/ folder for details.",
        )
        sys.exit(1)

    # 6. Create TradingGUI instance
    gui = None
    try:
        from ui.desktop import TradingGUI

        def engine_callback(action, **kwargs):
            """Bridge GUI button actions to engine start/stop methods."""
            if engine is None:
                return
            try:
                if action == "start":
                    engine.start()
                elif action == "stop":
                    engine.stop()
            except Exception as exc:
                logging.error("Engine callback '%s' failed: %s", action, exc)

        gui = TradingGUI(root, engine_callback=engine_callback)
        logging.info("TradingGUI created")
    except Exception as exc:
        logging.error("Failed to create TradingGUI: %s", exc, exc_info=True)
        messagebox.showerror(
            "GUI Error",
            f"Failed to initialise the GUI:\n{exc}\n\n"
            "Check the logs/ folder for details.",
        )
        sys.exit(1)

    # 7. Start GUI data polling (every 2 seconds)
    def poll_dashboard():
        """Periodically fetch dashboard data from engine and update GUI."""
        if engine is None or gui is None:
            return

        try:
            data = engine.get_dashboard_data()
            gui.update_data(data)
        except Exception as exc:
            logging.error("Dashboard poll error: %s", exc)

        # Schedule next poll
        if root.winfo_exists():
            root.after(2000, poll_dashboard)

    # Start polling after a short delay
    root.after(1000, poll_dashboard)
    logging.info("Dashboard polling started (every 2s)")

    # 8. AUTO-START engine
    def auto_start():
        """Start the engine automatically after GUI is ready."""
        if engine is None:
            return
        try:
            engine.start()
            if gui:
                gui.engine_running = True
                gui.broker_connected = True
                gui._set_indicator(True)
                gui.set_status("Engine: Running | Broker: Connected")
                logging.info("Engine auto-started successfully")
        except Exception as exc:
            logging.error("Engine auto-start failed: %s", exc, exc_info=True)
            if gui:
                gui.show_alert(
                    "Engine Error",
                    f"Engine failed to start:\n{exc}",
                )

    root.after(500, auto_start)

    # 9. Window close handler
    def on_close():
        """Handle window close — stop engine gracefully then destroy."""
        logging.info("Window close requested")

        # Stop engine
        if engine:
            try:
                engine.stop()
                logging.info("Engine stopped on close")
            except Exception as exc:
                logging.error("Engine stop failed: %s", exc)

        # Destroy window
        try:
            root.destroy()
        except Exception:
            pass

        logging.info("Application exited")
        sys.exit(0)

    root.protocol("WM_DELETE_WINDOW", on_close)

    # 10. Run main loop
    logging.info("Starting Tkinter main loop")
    root.mainloop()


# ======================================================================
# Entry point
# ======================================================================

if __name__ == "__main__":
    main()
