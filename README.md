# 📈 Stock Dashboard

A personal stock portfolio dashboard that runs locally on your desktop.
No internet accounts, no subscriptions, no ads — just your data, on your machine.

Built with Python, Streamlit, SQLite, and yfinance.

---

## What It Does

Stock Dashboard lets you track your personal investment portfolio in one place.
It pulls live market data automatically so your holdings, prices, and alerts
are always up to date.

---

## Features

### Portfolio
- Track buy and sell transactions manually or by importing a CSV export from Ameriprise
- Holdings table showing shares, average cost, market value, unrealized and realized gain/loss
- Per-holding transaction history
- Support for multiple accounts (e.g. Doug's IRA, Amy's IRA) with automatic account column
- Fetch current price button when adding or editing transactions

### Home Dashboard
- 3x2 summary cards: portfolio value, cost basis, holdings count, unrealized G/L, total G/L, day change
- Holdings snapshot table with live prices and day change %
- Latest news card with color-coded ticker badges
- Today's market movements and upcoming earnings

### Allocation
- Donut charts by ticker and sector
- Ticker weight table with account breakdown when multiple accounts are present
- Correlation matrix heatmap
- Concentration warning when any single holding exceeds a configurable threshold

### Watchlist
- Add tickers with optional target price alerts
- Technical signal flags: MA crossover (golden/death cross), RSI overbought/oversold, 52-week high/low proximity
- Move ticker to portfolio with account selection and live price fetch
- Auto-removes tickers from watchlist when they appear in a CSV import

### Dividends
- Annual dividend income per holding and total portfolio
- Upcoming ex-dividend dates
- Payment history and income-over-time chart

### Analytics
- Total return, annualized return (CAGR), and Sharpe ratio over selectable periods
- Portfolio vs S&P 500 (SPY) benchmark comparison chart
- Best and worst performers table
- Warning when transaction dates may be approximate due to CSV import limitations

### Charts
- Candlestick and line price charts with selectable date range
- Moving average overlays (50-day, 200-day)
- RSI and MACD panels
- Volume bar chart

### Earnings
- Upcoming earnings dates for all holdings and watchlist tickers
- Earnings this week flag with EPS estimate
- Past earnings with reported EPS, estimate, and surprise %
- Per-ticker earnings history

### Screener
- Configurable weighted scoring across P/E, EPS growth, momentum, analyst upside, and dividend yield
- Ranked results table
- Saveable scoring profiles
- Add to watchlist directly from results
- Non-advice disclaimer

### News
- Full news feed sorted most recent first
- Filter by ticker
- Configurable articles per ticker (adjustable on the page or in settings)
- Color-coded ticker badges (green = up today, red = down, blue = neutral)
- Clickable headlines open article in browser

### Notifications
- Session summary generated on app open: holdings movement, watchlist changes, upcoming earnings
- CSV import summaries showing new positions, closed positions, share count changes
- Bulk delete, select all, clear all with confirmation
- Desktop popup notifications via system notifications (Windows/Mac)

### Auto-Refresh & Idle Monitor
- Automatically checks prices when you haven't interacted with the app for a configurable time
- Fires desktop popup alerts when price movement thresholds are hit
- Configurable idle timeout and check interval in settings
- Per-alert toggles for holdings, watchlist, earnings, and dividends

### Settings
- Notification thresholds: price change %, RSI levels, earnings/dividend lead days
- Per-alert toggles and delivery method (in-app or desktop popup)
- Auto-refresh idle timeout and check interval
- Default screener weights
- Concentration warning threshold
- Sharpe ratio risk-free rate
- News articles per ticker
- CSV import info and weekly reminder
- Clear all data option with confirmation

### CSV Import (Ameriprise)
- Import from Ameriprise Unrealized Gain/Loss CSV export
- Detects changes since last import: new positions, closed positions, share count changes
- Supports multiple accounts — account column appears automatically when detected
- Auto-removes watchlist tickers that appear in the import
- Manual entry forms remain available alongside CSV import
- Change summary saved as a notification

---

## Possible Future Features

- **Email notifications** — send price alerts and session summaries to your email
- **Light/dark mode toggle** — currently uses Streamlit dark default
- **Plaid integration** — automatic sync with Ameriprise instead of CSV import
- **Realized gain/loss history chart** — visualize locked-in gains and losses over time
- **Tax lot tracking** — track individual purchase lots for tax-loss harvesting
- **Mobile-friendly layout** — optimized views for phone/tablet access
- **Multi-user support** — separate portfolios for different family members
- **Custom alerts** — set alerts on specific price levels per ticker
- **Options tracking** — track options positions alongside stock holdings
- **Export to PDF/Excel** — generate reports of your portfolio

---

## Requirements

- Windows 10/11 or macOS
- Python 3.10 or higher
- Internet connection (for live market data via yfinance)
- Ameriprise account (optional, for CSV import feature) - or any other stock management company or website that has a csv export feature, though some files like those in the utils folder will need to be changed to match the formatting of the csv file.

All Python package dependencies are installed automatically during setup.

---

## First Time Setup

### Step 1 — Install Python
Download and install Python 3.10 or higher from:
**https://www.python.org/downloads/**

> ⚠️ During installation, make sure to check **"Add Python to PATH"**

### Step 2 — Run Setup
Double-click **`setup.bat`** in the project folder.

This will:
- Create a virtual environment
- Install all required packages automatically

You only need to do this once.

### Step 3 — Launch the App
Double-click **`run_dashboard.vbs`** to open the app.

The app opens in its own window. No browser or terminal needed.

---

## Launching the App (Every Time)

Double-click **`run_dashboard.vbs`**

That's it. The app opens in its own window automatically.

To close the app, close the window.

---

## For Developers — Running from Terminal

If you want to modify the code or run the app from a terminal:

```bash
# Navigate to the project folder
cd stock-dashboard

# Activate the virtual environment
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

# Run the app
streamlit run Home.py

# Or use the launcher (opens in desktop window)
python launcher.py
```

---

## Project Structure
stock-dashboard/

├── Home.py                     # Home dashboard page

├── launcher.py                 # Desktop window launcher (pywebview)

├── run_dashboard.vbs           # Double-click launcher (Windows)

├── setup.bat                   # First time setup script

├── requirements.txt            # Python package dependencies

├── database.py                 # SQLite setup and all CRUD functions

├── data.py                     # yfinance wrappers with caching

├── pages/

│   ├── 1_Portfolio.py          # Transactions and holdings table

│   ├── 2_Allocation.py         # Allocation charts and correlation matrix

│   ├── 3_Watchlist.py          # Watchlist with technical signals

│   ├── 4_Dividends.py          # Dividend income and history

│   ├── 5_Analytics.py          # Returns, Sharpe ratio, benchmark comparison

│   ├── 6_Charts.py             # Price charts with indicators

│   ├── 7_Earnings.py           # Earnings dates and surprise history

│   ├── 8_Screener.py           # Weighted stock screener

│   ├── 9_News.py               # News feed

│   ├── 10_Notifications.py     # Session summaries and alerts

│   └── 11_Settings.py          # All app settings

├── db/

│   └── portfolio.db            # Local SQLite database (your data lives here)

└── utils/

├── metrics.py              # Return, Sharpe, correlation calculations

├── indicators.py           # MA, RSI, MACD calculations

├── theme.py                # CSS styling

├── price_monitor.py        # Idle price monitor and desktop alerts

└── csv_parser.py           # Ameriprise CSV import parser

---

## Your Data

All data is stored locally in `db/portfolio.db` — a single SQLite database file on your computer. Nothing is sent to any server. No accounts, no cloud storage.

To move your data to another computer, copy the `db/portfolio.db` file.

To start fresh, delete `db/portfolio.db` or use the "Clear All Data" option in Settings.

---

## Disclaimer

This app is for personal portfolio tracking only. Nothing in this app constitutes financial advice. All data is sourced from Yahoo Finance via yfinance and may be delayed or inaccurate. Always verify important financial information with your broker.
