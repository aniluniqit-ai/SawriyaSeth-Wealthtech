#!/usr/bin/env python3
"""
जय श्री सांवरीया सेठ — JSS Sawriya Seth Wealthtech AI Trading
Complete Tkinter Desktop GUI — Lite Theme
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import logging

# ---------------------------------------------------------------------------
# Lite Theme Colors
# ---------------------------------------------------------------------------
BG_COLOR       = "#FFFFFF"    # White background
PANEL_BG       = "#F8F9FA"    # Light gray panels
CARD_BG        = "#FFFFFF"    # White cards
TEXT_PRIMARY   = "#1A1A2E"    # Dark text
TEXT_SECONDARY = "#6B7280"    # Gray secondary text
ACCENT         = "#2563EB"    # Blue accent
GREEN          = "#16A34A"    # Profit green
RED            = "#DC2626"    # Loss red
ORANGE         = "#EA580C"    # Warning orange
BORDER         = "#E5E7EB"    # Light borders
HEADER_BG      = "#EFF6FF"    # Light blue header
CARD_BORDER    = "#D1D5DB"    # Card border
HOVER_BG       = "#F3F4F6"    # Hover background

# Log level colors (for Text widget tags)
LOG_COLORS = {
    "INFO":  "#2563EB",   # blue
    "WARN":  "#EA580C",   # orange
    "ERROR": "#DC2626",   # red
    "TRADE": "#16A34A",   # green
    "SYSTEM": "#6B7280",  # gray
    "DEBUG": "#9CA3AF",   # light gray
}

# Fonts — Segoe UI preferred, fallback to Arial / TkDefaultFont
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_FALLBACKS = ("Segoe UI", "Arial", "Helvetica", "DejaVu Sans")

FONTS = {
    "title":      (FONT_FAMILY, 14, "bold"),
    "subtitle":   (FONT_FAMILY, 11, "bold"),
    "heading":    (FONT_FAMILY, 10, "bold"),
    "body":       (FONT_FAMILY, 10),
    "body_bold":  (FONT_FAMILY, 10, "bold"),
    "small":      (FONT_FAMILY, 9),
    "small_bold": (FONT_FAMILY, 9, "bold"),
    "mono":       ("Consolas", 9),
    "mono_bold":  ("Consolas", 9, "bold"),
    "status":     (FONT_FAMILY, 9),
    "card_title": (FONT_FAMILY, 10, "bold"),
    "big_number": (FONT_FAMILY, 18, "bold"),
    "pnl_value":  (FONT_FAMILY, 13, "bold"),
    "label":      (FONT_FAMILY, 9),
    "log":        ("Consolas", 9),
}


class TradingGUI:
    """Full Tkinter desktop GUI for JSS Wealthtech AI Trading Platform."""

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def __init__(self, root: tk.Tk, engine_callback=None):
        self.root = root
        self.engine_callback = engine_callback  # callable: engine_callback(action, **kwargs)
        self.engine_running = False
        self.broker_connected = False
        self._last_log_index = 0  # track processed logs to avoid duplicates
        self._poll_after_id = None

        # Window setup
        self.root.title("जय श्री सांवरीया सेठ — JSS Wealthtech AI Trading")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1280x800")
        self.root.minsize(1024, 640)

        # Try to set a clean icon (graceful failure if missing)
        try:
            self.root.iconbitmap(default="")
        except Exception:
            pass

        # Build the GUI
        self._create_styles()
        self._create_title_bar()
        self._create_notebook()
        self._create_status_bar()

        # Auto-start engine on launch
        self.root.after(500, self._auto_start_engine)

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    def _create_styles(self):
        """Configure ttk styles for the lite theme."""
        self.style = ttk.Style()
        self.style.theme_use("clam")  # "clam" is the most customizable base

        # General
        self.style.configure(".", background=BG_COLOR, foreground=TEXT_PRIMARY,
                             fieldbackground=CARD_BG, borderwidth=0,
                             font=FONTS["body"])
        self.style.configure("TFrame", background=BG_COLOR)
        self.style.configure("Card.TFrame", background=CARD_BG)
        self.style.configure("Panel.TFrame", background=PANEL_BG)

        # Title bar
        self.style.configure("Title.TLabel", background=HEADER_BG,
                             foreground=ACCENT, font=FONTS["title"])
        self.style.configure("Status.TLabel", background=HEADER_BG,
                             foreground=TEXT_SECONDARY, font=FONTS["status"])

        # Notebook
        self.style.configure("TNotebook", background=BG_COLOR,
                             borderwidth=0, relief="flat")
        self.style.map("TNotebook", background=[("selected", BG_COLOR)])
        self.style.configure("TNotebook.Tab", background=PANEL_BG,
                             foreground=TEXT_SECONDARY, font=FONTS["body_bold"],
                             padding=[16, 8], borderwidth=0)
        self.style.map("TNotebook.Tab",
                        background=[("selected", CARD_BG)],
                        foreground=[("selected", ACCENT)])
        self.style.configure("TNotebook.Tab", padding=[20, 8])

        # Treeview — live market & trade history tables
        self.style.configure("Treeview",
                             background=CARD_BG,
                             foreground=TEXT_PRIMARY,
                             fieldbackground=CARD_BG,
                             font=FONTS["small"],
                             rowheight=24,
                             borderwidth=1)
        self.style.configure("Treeview.Heading",
                             background=HEADER_BG,
                             foreground=TEXT_PRIMARY,
                             font=FONTS["small_bold"],
                             relief="flat",
                             borderwidth=0)
        self.style.map("Treeview",
                        background=[("selected", "#DBEAFE")],
                        foreground=[("selected", TEXT_PRIMARY)])
        self.style.map("Treeview.Heading",
                        background=[("active", HEADER_BG)])

        # Buttons
        self.style.configure("TButton", font=FONTS["body"],
                             padding=[12, 6], borderwidth=1,
                             background=CARD_BG, foreground=TEXT_PRIMARY)
        self.style.map("TButton",
                        background=[("active", HOVER_BG)],
                        bordercolor=[("active", ACCENT)])
        self.style.configure("Accent.TButton",
                             background=ACCENT, foreground="#FFFFFF",
                             font=FONTS["body_bold"], borderwidth=0)
        self.style.map("Accent.TButton",
                        background=[("active", "#1D4ED8")])
        self.style.configure("Danger.TButton",
                             background=RED, foreground="#FFFFFF",
                             font=FONTS["body_bold"], borderwidth=0)
        self.style.map("Danger.TButton",
                        background=[("active", "#B91C1C")])
        self.style.configure("Success.TButton",
                             background=GREEN, foreground="#FFFFFF",
                             font=FONTS["body_bold"], borderwidth=0)
        self.style.map("Success.TButton",
                        background=[("active", "#15803D")])

        # Status bar
        self.style.configure("Status.TFrame", background=PANEL_BG)
        self.style.configure("StatusBar.TLabel", background=PANEL_BG,
                             foreground=TEXT_SECONDARY, font=FONTS["status"])

        # Combobox
        self.style.configure("TCombobox", font=FONTS["body"],
                             fieldbackground=CARD_BG, foreground=TEXT_PRIMARY)

        # Separator
        self.style.configure("TScrollbar", background=BORDER,
                             troughcolor=PANEL_BG, borderwidth=0,
                             arrowsize=14)
        self.style.map("TScrollbar",
                        background=[("active", TEXT_SECONDARY)])

        # Scale
        self.style.configure("TScale", background=BG_COLOR, troughcolor=BORDER)

    # ------------------------------------------------------------------
    # Title Bar
    # ------------------------------------------------------------------
    def _create_title_bar(self):
        """Create the top title bar with app name and status indicator."""
        self.title_bar = tk.Frame(self.root, bg=HEADER_BG, height=52)
        self.title_bar.pack(fill="x", side="top")
        self.title_bar.pack_propagate(False)

        # Left — App name
        left_frame = tk.Frame(self.title_bar, bg=HEADER_BG)
        left_frame.pack(side="left", padx=16, pady=8)

        tk.Label(left_frame, text="जय श्री सांवरीया सेठ",
                 bg=HEADER_BG, fg=ACCENT,
                 font=(FONT_FAMILY, 13, "bold")).pack(side="left", padx=(0, 6))
        tk.Label(left_frame, text="—",
                 bg=HEADER_BG, fg=TEXT_SECONDARY,
                 font=FONTS["title"]).pack(side="left", padx=(0, 6))
        tk.Label(left_frame, text="JSS Wealthtech",
                 bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=(FONT_FAMILY, 13, "bold")).pack(side="left", padx=(0, 4))
        tk.Label(left_frame, text="AI Trading",
                 bg=HEADER_BG, fg=TEXT_SECONDARY,
                 font=(FONT_FAMILY, 11)).pack(side="left")

        # Right — Status dot + label
        right_frame = tk.Frame(self.title_bar, bg=HEADER_BG)
        right_frame.pack(side="right", padx=16, pady=8)

        self.status_dot = tk.Canvas(right_frame, width=12, height=12,
                                    bg=HEADER_BG, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self._status_dot_item = self.status_dot.create_oval(2, 2, 10, 10,
                                                             fill=RED, outline="")

        self.status_label = tk.Label(right_frame, text="Stopped",
                                     bg=HEADER_BG, fg=RED,
                                     font=FONTS["small_bold"])
        self.status_label.pack(side="left")

        # Separator line
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.pack(fill="x", side="top")

    def _set_indicator(self, running: bool):
        """Update the title bar status dot and label."""
        color = GREEN if running else RED
        text = "Running" if running else "Stopped"
        self.status_dot.itemconfigure(self._status_dot_item, fill=color)
        self.status_label.configure(text=text, fg=color)

    # ------------------------------------------------------------------
    # Notebook (Tabs Container)
    # ------------------------------------------------------------------
    def _create_notebook(self):
        """Create the main ttk.Notebook with all tabs."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)

        self._create_dashboard_tab()
        self._create_trades_tab()
        self._create_settings_tab()
        self._create_ai_tab()

    # ------------------------------------------------------------------
    # TAB 1: Dashboard
    # ------------------------------------------------------------------
    def _create_dashboard_tab(self):
        """Create the Dashboard tab with capital, trade, market, and log panels."""
        dashboard = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(dashboard, text="  📊 Dashboard  ")

        # Configure grid: 2 columns, 2 rows. Top row is narrower.
        dashboard.columnconfigure(0, weight=1)
        dashboard.columnconfigure(1, weight=1)
        dashboard.rowconfigure(0, weight=0, minsize=220)
        dashboard.rowconfigure(1, weight=1)

        # TOP LEFT — Capital Panel
        self._build_capital_panel(dashboard)

        # TOP RIGHT — Current Trade Panel
        self._build_trade_panel(dashboard)

        # BOTTOM LEFT — Live Market Rates
        self._build_market_rates_panel(dashboard)

        # BOTTOM RIGHT — System Log
        self._build_system_log_panel(dashboard)

    # --- Capital Panel (top-left) ---
    def _build_capital_panel(self, parent):
        outer = tk.Frame(parent, bg=BG_COLOR, padx=6, pady=(6, 3))
        outer.grid(row=0, column=0, sticky="nsew")

        card = tk.Frame(outer, bg=CARD_BG, highlightbackground=CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(card, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="💰 Capital", bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=FONTS["card_title"]).pack(side="left", padx=12, pady=6)

        # Body
        body = tk.Frame(card, bg=CARD_BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        # Row 0 — Initial Capital
        tk.Label(body, text="Initial Capital", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=0, column=0, sticky="w", pady=2)
        self.lbl_initial_capital = tk.Label(body, text="₹1,000.00", bg=CARD_BG,
                                            fg=TEXT_PRIMARY, font=FONTS["body_bold"],
                                            anchor="e")
        self.lbl_initial_capital.grid(row=0, column=1, sticky="e", pady=2, padx=(20, 0))

        # Row 1 — Current Capital (big number)
        tk.Label(body, text="Current Capital", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.lbl_current_capital = tk.Label(body, text="₹1,000.00", bg=CARD_BG,
                                            fg=GREEN, font=FONTS["big_number"],
                                            anchor="e")
        self.lbl_current_capital.grid(row=1, column=1, sticky="e", pady=(8, 2), padx=(20, 0))

        # Row 2 — Today P&L
        tk.Label(body, text="Today P&L", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=2, column=0, sticky="w", pady=2)
        self.lbl_today_pnl = tk.Label(body, text="₹0.00", bg=CARD_BG,
                                      fg=TEXT_SECONDARY, font=FONTS["pnl_value"],
                                      anchor="e")
        self.lbl_today_pnl.grid(row=2, column=1, sticky="e", pady=2, padx=(20, 0))

        # Row 3 — Total P&L
        tk.Label(body, text="Total P&L", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=3, column=0, sticky="w", pady=2)
        self.lbl_total_pnl = tk.Label(body, text="₹0.00", bg=CARD_BG,
                                      fg=TEXT_SECONDARY, font=FONTS["body_bold"],
                                      anchor="e")
        self.lbl_total_pnl.grid(row=3, column=1, sticky="e", pady=2, padx=(20, 0))

        # Row 4 — Win Rate
        tk.Label(body, text="Win Rate", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=4, column=0, sticky="w", pady=2)
        self.lbl_win_rate = tk.Label(body, text="0%", bg=CARD_BG,
                                     fg=ACCENT, font=FONTS["body_bold"],
                                     anchor="e")
        self.lbl_win_rate.grid(row=4, column=1, sticky="e", pady=2, padx=(20, 0))

        # Row 5 — Trades
        tk.Label(body, text="Trades", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=5, column=0, sticky="w", pady=2)
        self.lbl_trades = tk.Label(body, text="0 (W: 0 / L: 0)", bg=CARD_BG,
                                   fg=TEXT_PRIMARY, font=FONTS["body_bold"],
                                   anchor="e")
        self.lbl_trades.grid(row=5, column=1, sticky="e", pady=2, padx=(20, 0))

        body.columnconfigure(1, weight=1)

    # --- Current Trade Panel (top-right) ---
    def _build_trade_panel(self, parent):
        outer = tk.Frame(parent, bg=BG_COLOR, padx=6, pady=(6, 3))
        outer.grid(row=0, column=1, sticky="nsew")

        card = tk.Frame(outer, bg=CARD_BG, highlightbackground=CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(card, bg=HEADER_BG)
        hdr.pack(fill="x")
        self.lbl_trade_status_header = tk.Label(hdr, text="📈 Current Trade",
                                                bg=HEADER_BG, fg=TEXT_PRIMARY,
                                                font=FONTS["card_title"])
        self.lbl_trade_status_header.pack(side="left", padx=12, pady=6)

        self.lbl_trade_badge = tk.Label(hdr, text="NONE", bg=HEADER_BG,
                                        fg=TEXT_SECONDARY, font=FONTS["small_bold"])
        self.lbl_trade_badge.pack(side="right", padx=12, pady=6)

        # Body
        body = tk.Frame(card, bg=CARD_BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)

        rows = [
            ("Status",    "trade_status"),
            ("Symbol",    "trade_symbol"),
            ("Direction", "trade_direction"),
            ("Entry",     "trade_entry"),
            ("LTP",       "trade_ltp"),
            ("SL",        "trade_sl"),
            ("Target",    "trade_target"),
            ("Trail SL",  "trade_trailing_sl"),
            ("P&L",       "trade_pnl"),
        ]

        self._trade_labels = {}
        for i, (label_text, key) in enumerate(rows):
            tk.Label(body, text=label_text, bg=CARD_BG,
                     fg=TEXT_SECONDARY, font=FONTS["label"],
                     anchor="w").grid(row=i, column=0, sticky="w", pady=2)
            lbl = tk.Label(body, text="—", bg=CARD_BG,
                           fg=TEXT_PRIMARY, font=FONTS["body_bold"],
                           anchor="e")
            lbl.grid(row=i, column=1, sticky="e", pady=2, padx=(20, 0))
            self._trade_labels[key] = lbl

        body.columnconfigure(1, weight=1)

    # --- Live Market Rates (bottom-left) ---
    def _build_market_rates_panel(self, parent):
        outer = tk.Frame(parent, bg=BG_COLOR, padx=6, pady=(3, 6))
        outer.grid(row=1, column=0, sticky="nsew")

        card = tk.Frame(outer, bg=CARD_BG, highlightbackground=CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(card, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📊 Live Market Rates", bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=FONTS["card_title"]).pack(side="left", padx=12, pady=6)

        # Treeview
        cols = ("symbol", "ltp", "change", "change_pct", "high", "low", "volume")
        self.market_tree = ttk.Treeview(card, columns=cols, show="headings",
                                        selectmode="browse", height=8)

        col_config = {
            "symbol":     ("Symbol",   100, "w"),
            "ltp":        ("LTP",       80, "e"),
            "change":     ("Change",    80, "e"),
            "change_pct": ("Change %",  80, "e"),
            "high":       ("High",      80, "e"),
            "low":        ("Low",       80, "e"),
            "volume":     ("Volume",    80, "e"),
        }

        for col, (heading, width, anchor) in col_config.items():
            self.market_tree.heading(col, text=heading)
            self.market_tree.column(col, width=width, minwidth=60, anchor=anchor,
                                    stretch=True)

        # Scrollbar
        market_scroll = ttk.Scrollbar(card, orient="vertical",
                                      command=self.market_tree.yview)
        self.market_tree.configure(yscrollcommand=market_scroll.set)

        self.market_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        market_scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)

        # Configure tag colors for positive/negative rows
        self.market_tree.tag_configure("up", foreground=GREEN)
        self.market_tree.tag_configure("down", foreground=RED)
        self.market_tree.tag_configure("flat", foreground=TEXT_SECONDARY)

    # --- System Log (bottom-right) ---
    def _build_system_log_panel(self, parent):
        outer = tk.Frame(parent, bg=BG_COLOR, padx=6, pady=(3, 6))
        outer.grid(row=1, column=1, sticky="nsew")

        card = tk.Frame(outer, bg=CARD_BG, highlightbackground=CARD_BORDER,
                        highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)

        # Header
        hdr = tk.Frame(card, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📋 System Log", bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=FONTS["card_title"]).pack(side="left", padx=12, pady=6)

        tk.Button(hdr, text="Clear", bg=PANEL_BG, fg=TEXT_SECONDARY,
                  font=FONTS["small"], bd=0, padx=8, pady=2, cursor="hand2",
                  activebackground=HOVER_BG, activeforeground=TEXT_PRIMARY,
                  command=self._clear_log).pack(side="right", padx=12, pady=4)

        # Text widget with scrollbar
        log_frame = tk.Frame(card, bg=CARD_BG)
        log_frame.pack(fill="both", expand=True, padx=6, pady=6)

        self.log_scroll = ttk.Scrollbar(log_frame, orient="vertical")
        self.log_text = tk.Text(log_frame, bg=CARD_BG, fg=TEXT_PRIMARY,
                                font=FONTS["log"], wrap="word", state="disabled",
                                bd=0, highlightthickness=1,
                                highlightbackground=BORDER,
                                insertbackground=TEXT_PRIMARY,
                                selectbackground="#DBEAFE",
                                padx=8, pady=4)

        self.log_scroll.configure(command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scroll.set)

        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_scroll.pack(side="right", fill="y")

        # Configure text tags for log levels
        for level, color in LOG_COLORS.items():
            self.log_text.tag_configure(level.lower(), foreground=color)
        self.log_text.tag_configure("timestamp", foreground=TEXT_SECONDARY)

    def _clear_log(self):
        """Clear the system log."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self._last_log_index = 0

    # ------------------------------------------------------------------
    # TAB 2: Trades History
    # ------------------------------------------------------------------
    def _create_trades_tab(self):
        """Create the Trade History tab with scrollable table."""
        tab = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(tab, text="  📈 Trades  ")

        # Header bar
        hdr = tk.Frame(tab, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📋 Trade History", bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=FONTS["subtitle"]).pack(side="left", padx=16, pady=8)

        self.lbl_total_trades_count = tk.Label(hdr, text="Total Trades: 0",
                                               bg=HEADER_BG, fg=TEXT_SECONDARY,
                                               font=FONTS["body"])
        self.lbl_total_trades_count.pack(side="right", padx=16, pady=8)

        # Treeview
        cols = ("time", "symbol", "direction", "strike", "entry", "exit",
                "pnl", "status", "strategy", "reason")

        self.trades_tree = ttk.Treeview(tab, columns=cols, show="headings",
                                        selectmode="browse", height=20)

        col_config = {
            "time":      ("Time",      80,  "w"),
            "symbol":    ("Symbol",    110, "w"),
            "direction": ("Dir",       50,  "center"),
            "strike":    ("Strike",    70,  "e"),
            "entry":     ("Entry",     80,  "e"),
            "exit":      ("Exit",      80,  "e"),
            "pnl":       ("P&L",       90,  "e"),
            "status":    ("Status",    70,  "center"),
            "strategy":  ("Strategy",  110, "w"),
            "reason":    ("Reason",    180, "w"),
        }

        for col, (heading, width, anchor) in col_config.items():
            self.trades_tree.heading(col, text=heading)
            self.trades_tree.column(col, width=width, minwidth=50, anchor=anchor,
                                    stretch=True)

        # Scrollbar
        trades_scroll_frame = tk.Frame(tab, bg=BG_COLOR)
        trades_scroll_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.trades_tree.pack(side="left", fill="both", expand=True,
                              in_=trades_scroll_frame)

        trades_vscroll = ttk.Scrollbar(trades_scroll_frame, orient="vertical",
                                       command=self.trades_tree.yview)
        trades_vscroll.pack(side="right", fill="y")
        self.trades_tree.configure(yscrollcommand=trades_vscroll.set)

        # Horizontal scrollbar
        trades_hscroll = ttk.Scrollbar(tab, orient="horizontal",
                                       command=self.trades_tree.xview)
        trades_hscroll.pack(fill="x", padx=8, pady=(0, 4))
        self.trades_tree.configure(xscrollcommand=trades_hscroll.set)

        # Tags
        self.trades_tree.tag_configure("profit", foreground=GREEN)
        self.trades_tree.tag_configure("loss", foreground=RED)
        self.trades_tree.tag_configure("open", foreground=ACCENT)
        self.trades_tree.tag_configure("header", background=HEADER_BG)

    # ------------------------------------------------------------------
    # TAB 3: Settings
    # ------------------------------------------------------------------
    def _create_settings_tab(self):
        """Create the Settings tab with engine controls and configuration."""
        tab = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(tab, text="  ⚙️ Settings  ")

        # Scrollable container
        canvas = tk.Canvas(tab, bg=BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_COLOR)

        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # --- Engine Control Card ---
        self._build_settings_card(scroll_frame, "🔄 Engine Control", 0)
        engine_body = tk.Frame(scroll_frame, bg=CARD_BG,
                               highlightbackground=CARD_BORDER, highlightthickness=1)
        engine_body.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))

        btn_frame = tk.Frame(engine_body, bg=CARD_BG)
        btn_frame.pack(fill="x", padx=16, pady=12)

        self.btn_start_engine = tk.Button(
            btn_frame, text="▶  Start Engine", bg=GREEN, fg="#FFFFFF",
            font=FONTS["body_bold"], bd=0, padx=20, pady=8, cursor="hand2",
            activebackground="#15803D", activeforeground="#FFFFFF",
            command=self._start_engine)
        self.btn_start_engine.pack(side="left", padx=(0, 8))

        self.btn_stop_engine = tk.Button(
            btn_frame, text="⏹  Stop Engine", bg=RED, fg="#FFFFFF",
            font=FONTS["body_bold"], bd=0, padx=20, pady=8, cursor="hand2",
            activebackground="#B91C1C", activeforeground="#FFFFFF",
            command=self._stop_engine, state="disabled")
        self.btn_stop_engine.pack(side="left")

        # Engine status
        self.lbl_engine_status = tk.Label(engine_body, text="Engine Status: Stopped",
                                          bg=CARD_BG, fg=RED, font=FONTS["body_bold"])
        self.lbl_engine_status.pack(padx=16, pady=(0, 4), anchor="w")

        # --- Strategy Card ---
        self._build_settings_card(scroll_frame, "📐 Strategy Selection", 2)
        strategy_body = tk.Frame(scroll_frame, bg=CARD_BG,
                                 highlightbackground=CARD_BORDER, highlightthickness=1)
        strategy_body.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

        strat_inner = tk.Frame(strategy_body, bg=CARD_BG)
        strat_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(strat_inner, text="Active Strategy:", bg=CARD_BG,
                 fg=TEXT_PRIMARY, font=FONTS["body"]).pack(side="left")

        self.strategy_var = tk.StringVar(value="momentum_follow")
        self.strategy_combo = ttk.Combobox(
            strat_inner, textvariable=self.strategy_var, state="readonly",
            values=["momentum_follow", "multi_scalping", "reversal_scalp",
                    "expiry_heropatla"],
            width=22, font=FONTS["body"])
        self.strategy_combo.pack(side="left", padx=(12, 0))

        # --- Capital Card ---
        self._build_settings_card(scroll_frame, "💰 Capital Information", 4)
        capital_body = tk.Frame(scroll_frame, bg=CARD_BG,
                                highlightbackground=CARD_BORDER, highlightthickness=1)
        capital_body.grid(row=5, column=0, sticky="ew", padx=16, pady=(0, 12))

        cap_inner = tk.Frame(capital_body, bg=CARD_BG)
        cap_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(cap_inner, text="Initial Capital:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).grid(row=0, column=0,
                                                               sticky="w", pady=2)
        tk.Label(cap_inner, text="₹1,000.00", bg=CARD_BG,
                 fg=TEXT_PRIMARY, font=FONTS["body_bold"]).grid(row=0, column=1,
                                                                  sticky="e", padx=(20, 0), pady=2)

        tk.Label(cap_inner, text="Current Capital:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).grid(row=1, column=0,
                                                               sticky="w", pady=2)
        self.settings_lbl_capital = tk.Label(cap_inner, text="₹1,000.00", bg=CARD_BG,
                                             fg=GREEN, font=FONTS["body_bold"])
        self.settings_lbl_capital.grid(row=1, column=1, sticky="e", padx=(20, 0), pady=2)

        tk.Label(cap_inner, text="Hard Floor:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).grid(row=2, column=0,
                                                               sticky="w", pady=2)
        tk.Label(cap_inner, text="₹100.00", bg=CARD_BG,
                 fg=RED, font=FONTS["body_bold"]).grid(row=2, column=1,
                                                        sticky="e", padx=(20, 0), pady=2)

        cap_inner.columnconfigure(1, weight=1)

        # --- Telegram Card ---
        self._build_settings_card(scroll_frame, "📨 Telegram", 6)
        tg_body = tk.Frame(scroll_frame, bg=CARD_BG,
                           highlightbackground=CARD_BORDER, highlightthickness=1)
        tg_body.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 12))

        tg_inner = tk.Frame(tg_body, bg=CARD_BG)
        tg_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(tg_inner, text="Alert Bot:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).pack(side="left")
        self.lbl_tg_bot_status = tk.Label(tg_inner, text="● Disconnected",
                                          bg=CARD_BG, fg=RED, font=FONTS["body_bold"])
        self.lbl_tg_bot_status.pack(side="left", padx=(8, 20))

        tk.Label(tg_inner, text="Signal Reader:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).pack(side="left")
        self.lbl_tg_reader_status = tk.Label(tg_inner, text="● Disconnected",
                                             bg=CARD_BG, fg=RED, font=FONTS["body_bold"])
        self.lbl_tg_reader_status.pack(side="left", padx=(8, 0))

        # --- Connection Card ---
        self._build_settings_card(scroll_frame, "🔌 Connection", 8)
        conn_body = tk.Frame(scroll_frame, bg=CARD_BG,
                             highlightbackground=CARD_BORDER, highlightthickness=1)
        conn_body.grid(row=9, column=0, sticky="ew", padx=16, pady=(0, 16))

        conn_inner = tk.Frame(conn_body, bg=CARD_BG)
        conn_inner.pack(fill="x", padx=16, pady=12)

        tk.Label(conn_inner, text="Broker:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).pack(side="left")
        self.lbl_broker_status = tk.Label(conn_inner, text="● Disconnected",
                                          bg=CARD_BG, fg=RED, font=FONTS["body_bold"])
        self.lbl_broker_status.pack(side="left", padx=(8, 20))

        tk.Label(conn_inner, text="Market:", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"]).pack(side="left")
        self.lbl_market_status = tk.Label(conn_inner, text="● Closed",
                                          bg=CARD_BG, fg=TEXT_SECONDARY,
                                          font=FONTS["body_bold"])
        self.lbl_market_status.pack(side="left", padx=(8, 0))

        scroll_frame.columnconfigure(0, weight=1)

    def _build_settings_card(self, parent, title, row):
        """Helper to build a settings card header."""
        lbl = tk.Label(parent, text=title, bg=BG_COLOR, fg=TEXT_PRIMARY,
                       font=FONTS["heading"], anchor="w")
        lbl.grid(row=row, column=0, sticky="ew", padx=16, pady=(12, 2))

    # ------------------------------------------------------------------
    # TAB 4: AI Analysis
    # ------------------------------------------------------------------
    def _create_ai_tab(self):
        """Create the AI Analysis tab with analysis text and confidence scores."""
        tab = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(tab, text="  🤖 AI Analysis  ")

        # Header
        hdr = tk.Frame(tab, bg=HEADER_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🤖 AI Market Analysis", bg=HEADER_BG, fg=TEXT_PRIMARY,
                 font=FONTS["subtitle"]).pack(side="left", padx=16, pady=8)

        self.lbl_ai_timestamp = tk.Label(hdr, text="", bg=HEADER_BG,
                                         fg=TEXT_SECONDARY, font=FONTS["status"])
        self.lbl_ai_timestamp.pack(side="right", padx=16, pady=8)

        # Split: left = analysis text, right = confidence scores
        content = tk.Frame(tab, bg=BG_COLOR)
        content.pack(fill="both", expand=True, padx=8, pady=8)

        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # --- Analysis Text ---
        analysis_card = tk.Frame(content, bg=CARD_BG,
                                 highlightbackground=CARD_BORDER, highlightthickness=1)
        analysis_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        analysis_hdr = tk.Frame(analysis_card, bg=HEADER_BG)
        analysis_hdr.pack(fill="x")
        tk.Label(analysis_hdr, text="📝 Latest Analysis", bg=HEADER_BG,
                 fg=TEXT_PRIMARY, font=FONTS["card_title"]).pack(side="left",
                                                                  padx=12, pady=6)

        self.ai_text = tk.Text(analysis_card, bg=CARD_BG, fg=TEXT_PRIMARY,
                               font=FONTS["mono"], wrap="word", state="disabled",
                               bd=0, highlightthickness=0, padx=12, pady=8,
                               insertbackground=TEXT_PRIMARY,
                               selectbackground="#DBEAFE")
        self.ai_text.pack(fill="both", expand=True)

        # Configure text tags
        self.ai_text.tag_configure("heading", font=("Consolas", 10, "bold"),
                                   foreground=ACCENT)
        self.ai_text.tag_configure("signal_buy", foreground=GREEN,
                                   font=("Consolas", 9, "bold"))
        self.ai_text.tag_configure("signal_sell", foreground=RED,
                                   font=("Consolas", 9, "bold"))
        self.ai_text.tag_configure("confidence_high", foreground=GREEN)
        self.ai_text.tag_configure("confidence_med", foreground=ORANGE)
        self.ai_text.tag_configure("confidence_low", foreground=RED)
        self.ai_text.tag_configure("separator", foreground=BORDER)

        # --- Confidence Scores Panel ---
        confidence_card = tk.Frame(content, bg=CARD_BG,
                                   highlightbackground=CARD_BORDER, highlightthickness=1)
        confidence_card.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        conf_hdr = tk.Frame(confidence_card, bg=HEADER_BG)
        conf_hdr.pack(fill="x")
        tk.Label(conf_hdr, text="📊 Confidence", bg=HEADER_BG,
                 fg=TEXT_PRIMARY, font=FONTS["card_title"]).pack(side="left",
                                                                  padx=12, pady=6)

        conf_body = tk.Frame(confidence_card, bg=CARD_BG)
        conf_body.pack(fill="both", expand=True, padx=12, pady=8)

        # Confidence metrics
        self._confidence_labels = {}
        metrics = [
            ("Overall", "overall"),
            ("Momentum", "momentum"),
            ("Trend", "trend"),
            ("Volatility", "volatility"),
            ("OI Signal", "oi"),
            ("RSI", "rsi"),
        ]

        for i, (label, key) in enumerate(metrics):
            tk.Label(conf_body, text=label, bg=CARD_BG, fg=TEXT_SECONDARY,
                     font=FONTS["label"], anchor="w").grid(row=i, column=0,
                                                           sticky="w", pady=3)

            # Progress bar
            style_name = f"{key}.Horizontal.TProgressbar"
            self.style.configure(style_name, troughcolor=PANEL_BG,
                                 background=ACCENT, thickness=16, borderwidth=0)
            bar = ttk.Progressbar(conf_body, style=style_name, length=120,
                                  maximum=100, mode="determinate")
            bar.grid(row=i, column=1, sticky="ew", padx=(8, 8), pady=3)
            bar["value"] = 0

            val_lbl = tk.Label(conf_body, text="0%", bg=CARD_BG,
                               fg=TEXT_PRIMARY, font=FONTS["small_bold"],
                               anchor="e", width=5)
            val_lbl.grid(row=i, column=2, sticky="e", pady=3)

            self._confidence_labels[key] = (bar, val_lbl)

        # Separator
        tk.Frame(conf_body, bg=BORDER, height=1).grid(row=len(metrics),
                                                       column=0, columnspan=3,
                                                       sticky="ew", pady=8)

        # Signal details
        signal_row = len(metrics) + 1
        tk.Label(conf_body, text="Latest Signal", bg=CARD_BG, fg=TEXT_SECONDARY,
                 font=FONTS["label"], anchor="w").grid(row=signal_row, column=0,
                                                       columnspan=3, sticky="w", pady=(4, 2))
        self.lbl_ai_signal = tk.Label(conf_body, text="No Signal", bg=CARD_BG,
                                      fg=TEXT_SECONDARY, font=FONTS["body_bold"],
                                      anchor="w", wraplength=200, justify="left")
        self.lbl_ai_signal.grid(row=signal_row + 1, column=0, columnspan=3,
                                sticky="w", pady=(0, 2))

        tk.Label(conf_body, text="Suggested Action", bg=CARD_BG,
                 fg=TEXT_SECONDARY, font=FONTS["label"],
                 anchor="w").grid(row=signal_row + 2, column=0, columnspan=3,
                                  sticky="w", pady=(8, 2))
        self.lbl_ai_action = tk.Label(conf_body, text="HOLD", bg=CARD_BG,
                                      fg=TEXT_SECONDARY, font=FONTS["body_bold"],
                                      anchor="w", wraplength=200, justify="left")
        self.lbl_ai_action.grid(row=signal_row + 3, column=0, columnspan=3,
                                sticky="w", pady=(0, 2))

        conf_body.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Status Bar (bottom)
    # ------------------------------------------------------------------
    def _create_status_bar(self):
        """Create the bottom status bar."""
        self.status_bar = tk.Frame(self.root, bg=PANEL_BG, height=28)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)

        # Separator above status bar
        sep = tk.Frame(self.root, bg=BORDER, height=1)
        sep.pack(fill="x", side="bottom", before=self.status_bar)

        # Left status
        self.status_left = tk.Label(self.status_bar,
                                    text="Engine: Stopped | Broker: Disconnected | Strategy: momentum_follow",
                                    bg=PANEL_BG, fg=TEXT_SECONDARY,
                                    font=FONTS["status"], anchor="w")
        self.status_left.pack(side="left", padx=12)

        # Right status (capital + time)
        self.status_right = tk.Label(self.status_bar,
                                     text="Capital: ₹1,000.00 | Time: --:--:--",
                                     bg=PANEL_BG, fg=TEXT_SECONDARY,
                                     font=FONTS["status"], anchor="e")
        self.status_right.pack(side="right", padx=12)

    # ------------------------------------------------------------------
    # Engine Control Actions
    # ------------------------------------------------------------------
    def _auto_start_engine(self):
        """Auto-start the engine 500ms after GUI initialization."""
        self._start_engine()

    def _start_engine(self):
        """Start the trading engine."""
        self.engine_running = True
        self._set_indicator(True)
        self.btn_start_engine.configure(state="disabled", bg=TEXT_SECONDARY)
        self.btn_stop_engine.configure(state="normal", bg=RED)
        self.lbl_engine_status.configure(text="Engine Status: ● Running", fg=GREEN)
        self.append_log("SYSTEM", "Engine started successfully")

        if self.engine_callback:
            try:
                self.engine_callback("start")
            except Exception as e:
                self.append_log("ERROR", f"Engine callback failed: {e}")

        self._update_clock()

    def _stop_engine(self):
        """Stop the trading engine."""
        self.engine_running = False
        self._set_indicator(False)
        self.btn_start_engine.configure(state="normal", bg=GREEN)
        self.btn_stop_engine.configure(state="disabled", bg=TEXT_SECONDARY)
        self.lbl_engine_status.configure(text="Engine Status: ● Stopped", fg=RED)
        self.append_log("SYSTEM", "Engine stopped by user")

        if self.engine_callback:
            try:
                self.engine_callback("stop")
            except Exception as e:
                self.append_log("ERROR", f"Engine callback failed: {e}")

    # ------------------------------------------------------------------
    # Clock Update
    # ------------------------------------------------------------------
    def _update_clock(self):
        """Update the clock in the status bar every second."""
        now = datetime.now().strftime("%H:%M:%S")
        current_text = self.status_right.cget("text")
        # Replace the time part (after "Time: ")
        parts = current_text.split("Time: ")
        if len(parts) == 2:
            self.status_right.configure(text=f"{parts[0]}Time: {now}")
        self.root.after(1000, self._update_clock)

    # ------------------------------------------------------------------
    # Data Update Methods (called every 2 seconds)
    # ------------------------------------------------------------------
    def update_data(self, data: dict):
        """
        Master update — called every 2 seconds with fresh data dict.

        Expected structure:
        {
            "capital_state": { initial, current, today_pnl, total_pnl,
                               win_rate, total_trades, wins, losses },
            "current_trade": { status, symbol, direction, entry, ltp,
                               sl, target, trailing_sl, pnl } | None,
            "market_data": [ { symbol, ltp, change, change_pct,
                               high, low, volume }, ... ],
            "logs": [ { level, message, timestamp }, ... ],
            "trades": [ { time, symbol, direction, strike, entry, exit,
                          pnl, status, strategy, reason }, ... ],
            "ai_analysis": { text, timestamp, confidence: { overall, momentum, ... },
                             signal, action },
        }
        """
        if not data:
            return

        # Capital
        capital = data.get("capital_state")
        if capital:
            self.update_capital_panel(capital)

        # Current trade
        trade = data.get("current_trade")
        if trade:
            self.update_trade_panel(trade)
        else:
            self._clear_trade_panel()

        # Market rates
        market = data.get("market_data")
        if market is not None:
            self.update_market_rates(market)

        # Logs
        logs = data.get("logs")
        if logs is not None:
            self.update_logs(logs)

        # Trades history
        trades = data.get("trades")
        if trades is not None:
            self.update_trades(trades)

        # AI Analysis
        ai = data.get("ai_analysis")
        if ai is not None:
            self.update_ai_analysis(ai)

    # --- Capital Panel ---
    def update_capital_panel(self, capital: dict):
        """Update all capital numbers with proper formatting and colors."""
        initial = capital.get("initial", 1000.0)
        current = capital.get("current", 1000.0)
        today_pnl = capital.get("today_pnl", 0.0)
        total_pnl = capital.get("total_pnl", 0.0)
        win_rate = capital.get("win_rate", 0.0)
        total_trades = capital.get("total_trades", 0)
        wins = capital.get("wins", 0)
        losses = capital.get("losses", 0)

        self.lbl_initial_capital.configure(text=self._format_currency(initial))

        # Current capital — green if profit, red if loss
        pnl_color = GREEN if current >= initial else RED
        self.lbl_current_capital.configure(
            text=self._format_currency(current), fg=pnl_color)

        # Today P&L
        today_color = self._color_for_pnl(today_pnl)
        today_sign = "+" if today_pnl > 0 else ""
        self.lbl_today_pnl.configure(
            text=f"{today_sign}{self._format_currency(today_pnl)}", fg=today_color)

        # Total P&L
        total_color = self._color_for_pnl(total_pnl)
        total_sign = "+" if total_pnl > 0 else ""
        self.lbl_total_pnl.configure(
            text=f"{total_sign}{self._format_currency(total_pnl)}", fg=total_color)

        # Win rate
        wr_color = GREEN if win_rate >= 50 else (ORANGE if win_rate >= 30 else RED)
        self.lbl_win_rate.configure(text=f"{win_rate:.1f}%", fg=wr_color)

        # Trades
        self.lbl_trades.configure(
            text=f"{total_trades} (W: {wins} / L: {losses})")

        # Settings capital
        self.settings_lbl_capital.configure(
            text=self._format_currency(current), fg=pnl_color)

        # Status bar capital
        self._update_status_bar_capital(current)

    # --- Trade Panel ---
    def update_trade_panel(self, trade: dict):
        """Update current trade display."""
        status = trade.get("status", "NONE")
        symbol = trade.get("symbol", "—")
        direction = trade.get("direction", "—")
        entry = trade.get("entry", 0)
        ltp = trade.get("ltp", 0)
        sl = trade.get("sl", 0)
        target = trade.get("target", 0)
        trailing_sl = trade.get("trailing_sl", 0)
        pnl = trade.get("pnl", 0)

        # Badge
        badge_colors = {"OPEN": GREEN, "CLOSED": TEXT_SECONDARY, "NONE": TEXT_SECONDARY}
        badge_color = badge_colors.get(status, TEXT_SECONDARY)
        self.lbl_trade_badge.configure(text=status, fg=badge_color)

        # Status
        status_colors = {"OPEN": GREEN, "CLOSED": ORANGE, "NONE": TEXT_SECONDARY}
        self._trade_labels["trade_status"].configure(
            text=status, fg=status_colors.get(status, TEXT_SECONDARY))

        # Symbol
        self._trade_labels["trade_symbol"].configure(text=symbol)

        # Direction
        dir_colors = {"BUY": GREEN, "SELL": RED}
        self._trade_labels["trade_direction"].configure(
            text=direction, fg=dir_colors.get(direction, TEXT_PRIMARY))

        # Entry
        self._trade_labels["trade_entry"].configure(
            text=self._format_currency(entry))

        # LTP
        self._trade_labels["trade_ltp"].configure(
            text=self._format_currency(ltp))

        # SL (red)
        self._trade_labels["trade_sl"].configure(
            text=self._format_currency(sl), fg=RED)

        # Target (green)
        self._trade_labels["trade_target"].configure(
            text=self._format_currency(target), fg=GREEN)

        # Trailing SL
        self._trade_labels["trade_trailing_sl"].configure(
            text=self._format_currency(trailing_sl) if trailing_sl else "—",
            fg=ORANGE if trailing_sl else TEXT_SECONDARY)

        # P&L
        pnl_color = self._color_for_pnl(pnl)
        pnl_sign = "+" if pnl > 0 else ""
        self._trade_labels["trade_pnl"].configure(
            text=f"{pnl_sign}{self._format_currency(pnl)}", fg=pnl_color)

    def _clear_trade_panel(self):
        """Clear current trade panel to default state."""
        self.lbl_trade_badge.configure(text="NONE", fg=TEXT_SECONDARY)
        for key, lbl in self._trade_labels.items():
            lbl.configure(text="—", fg=TEXT_PRIMARY)
        self._trade_labels["trade_sl"].configure(fg=RED)
        self._trade_labels["trade_target"].configure(fg=GREEN)

    # --- Market Rates ---
    def update_market_rates(self, data: list):
        """Update live market rates treeview."""
        # Clear existing items
        for item in self.market_tree.get_children():
            self.market_tree.delete(item)

        for row in data:
            symbol = row.get("symbol", "")
            ltp = row.get("ltp", 0)
            change = row.get("change", 0)
            change_pct = row.get("change_pct", 0)
            high = row.get("high", 0)
            low = row.get("low", 0)
            volume = row.get("volume", 0)

            # Determine tag based on change
            if change > 0:
                tag = "up"
            elif change < 0:
                tag = "down"
            else:
                tag = "flat"

            change_str = f"+{change:.2f}" if change > 0 else f"{change:.2f}"
            pct_str = f"+{change_pct:.2f}%" if change_pct > 0 else f"{change_pct:.2f}%"

            self.market_tree.insert("", "end", values=(
                symbol,
                self._format_currency(ltp),
                change_str,
                pct_str,
                self._format_currency(high),
                self._format_currency(low),
                f"{volume:,.0f}",
            ), tags=(tag,))

    # --- System Logs ---
    def update_logs(self, logs: list):
        """Add new log messages (only those not yet displayed)."""
        if not logs:
            return

        # Process only new logs
        new_logs = logs[self._last_log_index:]
        self._last_log_index = len(logs)

        for log_entry in new_logs:
            level = log_entry.get("level", "INFO").upper()
            message = log_entry.get("message", "")
            timestamp = log_entry.get("timestamp",
                                      datetime.now().strftime("%H:%M:%S"))

            self.append_log(level, message, timestamp)

    def append_log(self, level: str, message: str, timestamp: str = None):
        """Add a single log message to the log widget."""
        if timestamp is None:
            timestamp = datetime.now().strftime("%H:%M:%S")

        self.log_text.configure(state="normal")

        # Timestamp
        self.log_text.insert("end", f"[{timestamp}] ", "timestamp")

        # Level tag
        tag = level.lower() if level.lower() in LOG_COLORS else "system"
        self.log_text.insert("end", f"{level:>5} ", tag)

        # Message
        self.log_text.insert("end", f"  {message}\n")

        self.log_text.configure(state="disabled")

        # Auto-scroll to bottom
        self.log_text.see("end")

    # --- Trade History ---
    def update_trades(self, trades: list):
        """Refresh the trade history table."""
        # Clear existing
        for item in self.trades_tree.get_children():
            self.trades_tree.delete(item)

        count = 0
        for trade in trades:
            pnl = trade.get("pnl", 0)
            status = trade.get("status", "")

            # Determine tag
            if status == "OPEN":
                tag = "open"
            elif pnl > 0:
                tag = "profit"
            elif pnl < 0:
                tag = "loss"
            else:
                tag = ""

            pnl_str = f"+{self._format_currency(pnl)}" if pnl > 0 else self._format_currency(pnl)

            self.trades_tree.insert("", "end", values=(
                trade.get("time", ""),
                trade.get("symbol", ""),
                trade.get("direction", ""),
                trade.get("strike", ""),
                self._format_currency(trade.get("entry", 0)),
                self._format_currency(trade.get("exit", 0)) if trade.get("exit") else "—",
                pnl_str,
                status,
                trade.get("strategy", ""),
                trade.get("reason", ""),
            ), tags=(tag,))

            count += 1

        self.lbl_total_trades_count.configure(text=f"Total Trades: {count}")

    # --- AI Analysis ---
    def update_ai_analysis(self, ai: dict):
        """Update the AI analysis tab with latest analysis."""
        text = ai.get("text", "")
        timestamp = ai.get("timestamp", "")
        confidence = ai.get("confidence", {})
        signal = ai.get("signal", "No Signal")
        action = ai.get("action", "HOLD")

        # Timestamp
        if timestamp:
            self.lbl_ai_timestamp.configure(text=f"Updated: {timestamp}")

        # Analysis text
        self.ai_text.configure(state="normal")
        self.ai_text.delete("1.0", "end")
        if text:
            # Insert with basic formatting
            self.ai_text.insert("end", text + "\n")
        else:
            self.ai_text.insert("end", "Awaiting analysis...\n", "confidence_low")
        self.ai_text.configure(state="disabled")

        # Confidence scores
        for key, (bar, val_lbl) in self._confidence_labels.items():
            value = confidence.get(key, 0)
            value = max(0, min(100, value))  # clamp
            bar["value"] = value

            # Color based on value
            if value >= 70:
                color = GREEN
            elif value >= 40:
                color = ORANGE
            else:
                color = RED

            val_lbl.configure(text=f"{value:.0f}%", fg=color)

            # Update bar color
            style_name = f"{key}.Horizontal.TProgressbar"
            self.style.configure(style_name, background=color)

        # Signal
        signal_colors = {"BUY": GREEN, "SELL": RED, "HOLD": TEXT_SECONDARY}
        signal_color = signal_colors.get(signal, TEXT_SECONDARY)
        self.lbl_ai_signal.configure(text=str(signal), fg=signal_color)

        # Action
        action_colors = {"BUY": GREEN, "SELL": RED, "HOLD": TEXT_SECONDARY,
                         "WAIT": ORANGE}
        action_color = action_colors.get(action, TEXT_SECONDARY)
        self.lbl_ai_action.configure(text=str(action), fg=action_color)

    # ------------------------------------------------------------------
    # Status Bar Update
    # ------------------------------------------------------------------
    def set_status(self, text: str):
        """Update the left side of the status bar."""
        self.status_left.configure(text=text)

    def _update_status_bar_capital(self, capital: float):
        """Update capital display in status bar."""
        current_text = self.status_right.cget("text")
        parts = current_text.split("Capital: ")
        if len(parts) == 2:
            cap_time = parts[1]
            time_parts = cap_time.split("Time: ")
            new_text = f"{parts[0]}Capital: {self._format_currency(capital)}"
            if len(time_parts) == 2:
                new_text += f" | Time: {time_parts[1]}"
            self.status_right.configure(text=new_text)

    # ------------------------------------------------------------------
    # Alert / Popup
    # ------------------------------------------------------------------
    def show_alert(self, title: str, message: str):
        """Show a popup alert dialog."""
        messagebox.showinfo(title, message, parent=self.root)

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------
    @staticmethod
    def _format_currency(amount: float) -> str:
        """Format a number as Indian-style ₹ currency string."""
        try:
            amount = float(amount)
            # Indian number formatting: e.g., 1,25,000.00
            s = f"{amount:,.2f}"
            # Split integer and decimal parts
            if "." in s:
                int_part, dec_part = s.split(".", 1)
            else:
                int_part = s
                dec_part = "00"

            # Remove existing commas and reformat Indian style
            int_part = int_part.replace(",", "")
            if len(int_part) > 3:
                last_three = int_part[-3:]
                rest = int_part[:-3]
                # Insert commas every 2 digits from the right
                formatted_rest = ""
                for i, ch in enumerate(reversed(rest)):
                    if i > 0 and i % 2 == 0:
                        formatted_rest = "," + formatted_rest
                    formatted_rest = ch + formatted_rest
                int_part = formatted_rest + "," + last_three

            return f"₹{int_part}.{dec_part}"
        except (ValueError, TypeError):
            return "₹0.00"

    @staticmethod
    def _color_for_pnl(pnl: float) -> str:
        """Return green if positive P&L, red if negative, gray if zero."""
        if pnl > 0:
            return GREEN
        elif pnl < 0:
            return RED
        return TEXT_SECONDARY


# -----------------------------------------------------------------------
# Demo / Standalone runner
# -----------------------------------------------------------------------
def _demo_data():
    """Generate demo data for testing the GUI standalone."""
    import random
    random.seed(42)

    base_capital = 1000.0
    pnl = random.uniform(-100, 250)
    current = max(100.0, base_capital + pnl)

    capital_state = {
        "initial": base_capital,
        "current": current,
        "today_pnl": pnl * 0.4,
        "total_pnl": pnl,
        "win_rate": random.uniform(30, 80),
        "total_trades": random.randint(5, 25),
        "wins": random.randint(2, 15),
        "losses": random.randint(1, 10),
    }

    has_trade = random.random() > 0.3
    if has_trade:
        entry = random.uniform(100, 300)
        ltp = entry * random.uniform(0.95, 1.08)
        sl = entry * 0.97
        target = entry * 1.05
        current_trade = {
            "status": "OPEN",
            "symbol": "NIFTY 24500 CE",
            "direction": random.choice(["BUY", "SELL"]),
            "entry": round(entry, 2),
            "ltp": round(ltp, 2),
            "sl": round(sl, 2),
            "target": round(target, 2),
            "trailing_sl": round(sl * 1.005, 2) if random.random() > 0.5 else 0,
            "pnl": round((ltp - entry) * 50, 2),
        }
    else:
        current_trade = None

    market_data = []
    for sym, base in [("NIFTY", 24450), ("BANKNIFTY", 51200), ("FINNIFTY", 23100)]:
        ltp = base + random.uniform(-100, 100)
        chg = random.uniform(-50, 50)
        market_data.append({
            "symbol": sym,
            "ltp": round(ltp, 2),
            "change": round(chg, 2),
            "change_pct": round(chg / base * 100, 2),
            "high": round(ltp + abs(chg), 2),
            "low": round(ltp - abs(chg), 2),
            "volume": random.randint(100000, 5000000),
        })

    now = datetime.now()
    logs = [
        {"level": "SYSTEM", "message": "Engine initialized successfully",
         "timestamp": (now.replace(second=0)).strftime("%H:%M:%S")},
        {"level": "INFO", "message": "Market session started",
         "timestamp": (now.replace(second=1)).strftime("%H:%M:%S")},
        {"level": "TRADE", "message": "BUY NIFTY 24500 CE @ 185.50 | SL: 179.00 | TGT: 196.00",
         "timestamp": (now.replace(second=5)).strftime("%H:%M:%S")},
        {"level": "WARN", "message": "RSI approaching overbought zone (69.5)",
         "timestamp": (now.replace(second=10)).strftime("%H:%M:%S")},
        {"level": "INFO", "message": "Capital check passed: ₹1,000.00 available",
         "timestamp": (now.replace(second=15)).strftime("%H:%M:%S")},
    ]

    trades = [
        {"time": "10:30:15", "symbol": "NIFTY 24450 CE", "direction": "BUY",
         "strike": "24450", "entry": 178.50, "exit": 192.00, "pnl": 675.00,
         "status": "CLOSED", "strategy": "momentum_follow",
         "reason": "Target achieved"},
        {"time": "11:15:42", "symbol": "NIFTY 24500 CE", "direction": "BUY",
         "strike": "24500", "entry": 185.50, "exit": 0, "pnl": 0,
         "status": "OPEN", "strategy": "momentum_follow",
         "reason": "Momentum signal"},
        {"time": "13:05:30", "symbol": "BANKNIFTY 51000 PE", "direction": "SELL",
         "strike": "51000", "entry": 210.00, "exit": 225.00, "pnl": -375.00,
         "status": "CLOSED", "strategy": "reversal_scalp",
         "reason": "Stop loss hit"},
    ]

    ai_analysis = {
        "text": (
            "═══ AI Market Analysis ═══\n\n"
            "Market Trend: BULLISH\n"
            "NIFTY showing strong upward momentum with EMA 9 > EMA 21.\n"
            "RSI at 58.3 — Room for further upside.\n"
            "MACD histogram turning positive — Bullish crossover.\n"
            "SuperTrend: UP (Support at 24,320)\n"
            "ADX: 32.5 — Strong trend confirmed.\n\n"
            "OI Analysis:\n"
            "  Max CE OI: 24,500 (Resistance)\n"
            "  Max PE OI: 24,300 (Support)\n"
            "  PCR: 1.35 (Bullish)\n\n"
            "Recommendation: BUY NIFTY 24500 CE\n"
            "Confidence: 78%\n"
            "Risk-Reward: 1:1.8"
        ),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "confidence": {
            "overall": 78,
            "momentum": 82,
            "trend": 75,
            "volatility": 60,
            "oi": 70,
            "rsi": 65,
        },
        "signal": "BUY NIFTY 24500 CE",
        "action": "BUY",
    }

    return {
        "capital_state": capital_state,
        "current_trade": current_trade,
        "market_data": market_data,
        "logs": logs,
        "trades": trades,
        "ai_analysis": ai_analysis,
    }


def _demo_poll(gui: TradingGUI):
    """Demo polling loop that updates with simulated data every 2 seconds."""
    import random
    iteration = 0

    def _poll():
        nonlocal iteration
        iteration += 1
        data = _demo_data()

        # Simulate some variation
        data["capital_state"]["current"] += random.uniform(-5, 5)
        data["capital_state"]["current"] = max(100.0,
                                                data["capital_state"]["current"])
        data["capital_state"]["today_pnl"] = (
            data["capital_state"]["current"] - data["capital_state"]["initial"]
        ) * 0.4

        if data["current_trade"]:
            data["current_trade"]["ltp"] += random.uniform(-3, 3)

        # Add periodic log
        if iteration % 3 == 0:
            import random as _r
            levels = ["INFO", "INFO", "TRADE", "WARN"]
            msgs = [
                "Option chain refreshed — 45 strikes loaded",
                "ATM strike detected: 24,500",
                "Trailing SL updated to 180.50",
                "Checking momentum alignment...",
                "Capital utilization: 42%",
                "Waiting for signal confirmation",
            ]
            data["logs"].append({
                "level": _r.choice(levels),
                "message": _r.choice(msgs),
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })

        gui.update_data(data)

        # Continue polling
        gui.root.after(2000, _poll)

    # Start polling after 1 second
    gui.root.after(1000, _poll)


def main():
    """Launch the GUI application."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    logging.info("Starting JSS Wealthtech AI Trading GUI...")

    root = tk.Tk()

    # On Windows, enable DPI awareness for crisp rendering
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    gui = TradingGUI(root)

    # Start demo polling for standalone testing
    _demo_poll(gui)

    root.protocol("WM_DELETE_WINDOW", lambda: (root.quit(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
