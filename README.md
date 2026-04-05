# 🪷 JSS Sawriya Seth Wealthtech — AI Options Trading System

<p align="center">
  <strong>जय श्री सांवरीया सेठ</strong><br>
  <em>Intelligent Paper Trading Platform with AI-Powered Signal Scoring</em>
</p>

---

## 📋 Overview

**JSS Sawriya Seth Wealthtech** is a comprehensive AI-powered options trading platform designed for the Indian derivatives market (NIFTY, BANKNIFTY, FINNIFTY). It runs entirely in **paper trading mode** — no real money is at risk — making it the perfect tool for learning, backtesting strategies, and developing trading skills.

The system uses multiple technical indicators and strategies to generate trading signals, manages capital with strict risk controls, and provides a beautiful desktop GUI with real-time monitoring.

## ✨ Features

### 🧠 AI-Powered Trading Engine
- **4 Trading Strategies**: Momentum Follow, Multi Scalping, Reversal Scalp, Expiry Day Hero Patla
- **10+ Technical Indicators**: EMA, RSI, MACD, SuperTrend, Bollinger Bands, ATR, VWAP, ADX, and more
- **AI Scoring System**: Combines momentum, trend, volatility, OI, and RSI into an overall confidence score
- **Automatic Signal Generation**: Scans market every 3 seconds during trading hours

### 💰 Capital Management
- **₹100 Hard Floor**: Capital can NEVER go below ₹100
- **Dynamic Lot Sizing**: Scales lots based on account growth
- **Daily Loss Limits**: Configurable maximum daily loss percentage
- **Max Open Trades**: Limits concurrent positions (default: 3)

### 🛡️ Risk Management
- **Stop-Loss**: Automatic SL calculation based on entry price
- **Target**: Risk-reward ratio-based target calculation
- **Trailing Stop-Loss**: Activates after favourable price movement
- **Time-Based Exit**: Auto square-off at 15:15 IST
- **Strategy Cooldowns**: Pause strategies after losses
- **Consecutive Loss Limit**: Pause trading after N consecutive losses

### 📊 Live Market Data
- **Real-time LTP**: Live prices via Kotak Neo Securities API
- **OHLCV Candles**: 1-minute candle data (100 candles)
- **Option Chain**: Full CE/PE chain with OI, IV, volume analysis
- **OI Analysis**: Put-Call Ratio, max OI strikes, sentiment detection
- **Premium Analysis**: ATM premiums, IV skew, cheapest options

### 📨 Telegram Integration
- **Alert Bot**: Sends trade open/close alerts and daily reports
- **Signal Reader**: Reads trading signals from Telegram groups
- **Signal Parser**: Parses messy Telegram messages into structured signals
- **Supported Formats**: BUY NIFTY 24500 CE, SHORT BANKNIFTY 51000 PE SL 190 TGT 170, etc.

### 🖥️ Desktop GUI
- **Dashboard Tab**: Capital panel, current trade, live market rates, system log
- **Trades Tab**: Full trade history with profit/loss color coding
- **Settings Tab**: Engine controls, strategy selection, connection status
- **AI Analysis Tab**: Confidence scores, trend analysis, suggested actions
- **Lite White Theme**: Clean, professional design
- **Auto-Start**: Engine starts automatically on launch

### 📈 Daily Reports
- **Auto-Generated**: Daily P&L, win rate, best strategy
- **Excel Export**: Detailed reports with openpyxl formatting
- **Telegram Reports**: End-of-day summary sent via Telegram

## 🚀 Installation

### Prerequisites
- **Python 3.10+** (3.10, 3.11, or 3.12 recommended)
- **Windows 10/11** (for .bat launcher scripts)
- **Internet connection** (for market data)

### Steps

1. **Clone or download** the project folder.

2. **Install dependencies**:
   ```
   Double-click: Install.bat
   ```
   Or manually:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure** `config/config.json` with your Kotak Neo credentials.

4. **Run the application**:
   ```
   Double-click: Start.bat
   ```
   Or manually:
   ```bash
   python omai_main.py
   ```

## ⚙️ Configuration

Edit `config/config.json` to configure the system:

### Broker Settings (Kotak Neo Securities)
```json
{
  "broker": {
    "client_code": "YOUR_6_DIGIT_CODE",
    "access_token": "YOUR_ACCESS_TOKEN",
    "mobile": "YOUR_10_DIGIT_MOBILE",
    "mpin": "YOUR_MPIN",
    "totp_secret": "YOUR_BASE32_TOTP_SECRET"
  }
}
```

### Capital Settings
```json
{
  "capital": {
    "initial_capital": 1000.0,
    "max_daily_loss_percent": 5.0,
    "max_open_trades": 3,
    "scale_capital_threshold": 10000.0
  }
}
```

### Risk Settings
```json
{
  "risk": {
    "sl_percent": 15.0,
    "risk_reward_ratio": 2.0,
    "trailing_sl_activation_pct": 3.0,
    "trailing_sl_trail_pct": 1.5,
    "max_consecutive_losses": 3,
    "strategy_cooldown_minutes": 15
  }
}
```

### Telegram Settings
```json
{
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_BOT_TOKEN_FROM_BOTFATHER",
    "chat_id": "YOUR_CHAT_ID",
    "reader_enabled": false,
    "api_id": 0,
    "api_hash": "",
    "phone": "",
    "groups_to_watch": []
  }
}
```

## 📁 Folder Structure

```
jss-wealthtech/
├── omai_main.py              # Main entry point — run this!
├── config/
│   └── config.json           # Configuration file
├── core/
│   ├── __init__.py           # Package exports
│   ├── engine.py             # Main trading engine (brain)
│   ├── db_helper.py          # SQLite database helper
│   ├── indicators.py         # Technical indicators
│   ├── option_chain.py       # Option chain analyzer
│   ├── capital.py            # Capital manager
│   └── risk.py               # Risk manager
├── brokers/
│   ├── __init__.py           # Package exports
│   ├── kotak_neo.py          # Kotak Neo broker (paper trading)
│   └── session_manager.py    # Session persistence
├── strategies/
│   ├── __init__.py           # Package marker
│   ├── base_strategy.py      # Abstract base strategy
│   ├── momentum_follow.py    # Momentum following strategy
│   ├── multi_scalping.py     # Multi-indicator scalping
│   ├── reversal_scalp.py     # RSI reversal strategy
│   └── expiry_heropatla.py   # Expiry day special strategy
├── telegram/
│   ├── __init__.py           # Package marker
│   ├── bot.py                # Telegram alert bot
│   ├── reader.py             # Telegram group reader
│   └── parser.py             # Signal parser
├── ui/
│   ├── __init__.py           # Package marker
│   └── desktop.py            # Tkinter desktop GUI
├── data/
│   ├── jss_trading.db        # SQLite database (auto-created)
│   ├── sessions/             # Broker session files
│   └── telegram/             # Telegram session files
├── logs/
│   └── jss_trading.log       # Application log (auto-created)
├── reports/                  # Daily Excel reports (auto-generated)
├── images/
│   └── app_icon.ico          # Application icon
├── requirements.txt          # Python dependencies
├── Install.bat               # Windows: Install dependencies
├── Start.bat                 # Windows: Launch application
├── Build_OneFile.bat         # Windows: Build standalone EXE
└── README.md                 # This file
```

## 🎮 How to Use

1. **First Launch**: Run `Start.bat` — the app will create a default `config.json` if missing.

2. **Configure Broker**: Edit `config/config.json` with your Kotak Neo credentials.

3. **Watch it Trade**: The engine auto-starts and begins scanning the market during trading hours (09:15–15:30 IST).

4. **Monitor**: Use the Dashboard tab to watch capital, trades, and market data in real-time.

5. **Review Trades**: Switch to the Trades tab to see full trade history.

6. **AI Insights**: Check the AI Analysis tab for confidence scores and suggested actions.

7. **Settings**: Toggle strategies, check connection status, and manage engine from the Settings tab.

8. **Daily Reports**: After market close (15:30 IST), the system auto-generates a report in the `reports/` folder.

## 🏗️ Building Standalone EXE

To create a single-file Windows executable:

```
Double-click: Build_OneFile.bat
```

The resulting EXE will be in `dist/JSS_Wealthtech_AI_Trading.exe`.  
**Important**: Copy the `config/` and `images/` folders next to the EXE before running.

## 📸 Screenshots

> Screenshots will be added here.

## 🔧 Technologies

- **Python 3.10+** — Core language
- **Tkinter** — Desktop GUI
- **SQLite** — Local database
- **Kotak Neo API** — Market data (paper trading)
- **python-telegram-bot** — Alert notifications
- **Telethon** — Telegram group reader
- **openpyxl** — Excel report generation
- **numpy** — Fast numerical calculations

## ⚠️ Disclaimer

> **This is a PAPER TRADING system. No real orders are sent to the exchange. No real money is at risk.**  
> This software is for educational and research purposes only. Trading in options involves significant risk. Past performance (even in paper trading) does not guarantee future results. Always consult a qualified financial advisor before trading with real money.

## 📄 License

This project is proprietary software. All rights reserved by JSS Sawriya Seth Wealthtech.

---

<p align="center">
  <strong>🪷 जय श्री सांवरीया सेठ 🪷</strong>
</p>
