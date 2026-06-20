import streamlit as st
from database import (
    initialize_db,
    get_setting,
    set_setting,
    delete_all_notifications,
    get_transactions,
    get_watchlist,
)
import sqlite3
import os

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Settings", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Settings")

# ── Helper ────────────────────────────────────────────────────────────────────

def s(key, default):
    """Shorthand to get a setting with a default."""
    return get_setting(key, default)


# ── Appearance ────────────────────────────────────────────────────────────────

st.subheader("Appearance")

theme = s("theme", "Light")
new_theme = st.radio("Theme", ["Light", "Dark"], index=0 if theme == "Light" else 1, horizontal=True)
if new_theme != theme:
    set_setting("theme", new_theme)
    st.rerun()

st.divider()

# ── Notification thresholds ───────────────────────────────────────────────────

st.subheader("Notification Thresholds")
st.caption("Controls what triggers a notification entry on the Notifications page.")

col1, col2 = st.columns(2)

with col1:
    price_change_pct = st.number_input(
        "Holdings price change % to flag",
        min_value=0.1, max_value=50.0,
        value=float(str(s("notify_price_change_pct", "2.0"))),
        step=0.5, format="%.1f",
    )
    watchlist_change_pct = st.number_input(
        "Watchlist price change % to flag",
        min_value=0.1, max_value=50.0,
        value=float(str(s("notify_watchlist_change_pct", "1.0"))),
        step=0.5, format="%.1f",
    )
    earnings_lead_days = st.number_input(
        "Earnings warning lead days",
        min_value=1, max_value=30,
        value=int(str(s("notify_earnings_lead_days", "7"))),
        step=1,
    )

with col2:
    dividend_lead_days = st.number_input(
        "Dividend ex-date warning lead days",
        min_value=1, max_value=30,
        value=int(str(s("notify_dividend_lead_days", "7"))),
        step=1,
    )
    rsi_overbought = st.number_input(
        "RSI overbought threshold",
        min_value=50, max_value=95,
        value=int(str(s("notify_rsi_overbought", "70"))),
        step=1,
    )
    rsi_oversold = st.number_input(
        "RSI oversold threshold",
        min_value=5, max_value=50,
        value=int(str(s("notify_rsi_oversold", "30"))),
        step=1,
    )

st.markdown("**Per-alert toggles**")
tog1, tog2, tog3, tog4 = st.columns(4)
notify_holdings = tog1.toggle("Holdings movement", value=s("notify_holdings", "1") == "1")
notify_watchlist = tog2.toggle("Watchlist changes", value=s("notify_watchlist", "1") == "1")
notify_earnings = tog3.toggle("Earnings alerts", value=s("notify_earnings", "1") == "1")
notify_dividends = tog4.toggle("Dividend alerts", value=s("notify_dividends", "1") == "1")

if st.button("Save Notification Settings"):
    set_setting("notify_price_change_pct", str(price_change_pct))
    set_setting("notify_watchlist_change_pct", str(watchlist_change_pct))
    set_setting("notify_earnings_lead_days", str(earnings_lead_days))
    set_setting("notify_dividend_lead_days", str(dividend_lead_days))
    set_setting("notify_rsi_overbought", str(rsi_overbought))
    set_setting("notify_rsi_oversold", str(rsi_oversold))
    set_setting("notify_holdings", "1" if notify_holdings else "0")
    set_setting("notify_watchlist", "1" if notify_watchlist else "0")
    set_setting("notify_earnings", "1" if notify_earnings else "0")
    set_setting("notify_dividends", "1" if notify_dividends else "0")
    st.success("Notification settings saved.")

st.divider()

# ── Screener weights ──────────────────────────────────────────────────────────

st.subheader("Default Screener Weights")
st.caption("These are the default weights loaded when no saved profile is selected in the Screener.")

sw1, sw2, sw3, sw4, sw5 = st.columns(5)
w_pe = sw1.slider("P/E", 0.0, 3.0, float(str(s("screener_w_pe", "1.0"))), 0.5)
w_growth = sw2.slider("EPS Growth", 0.0, 3.0, float(str(s("screener_w_growth", "1.0"))), 0.5)
w_momentum = sw3.slider("Momentum", 0.0, 3.0, float(str(s("screener_w_momentum", "1.0"))), 0.5)
w_upside = sw4.slider("Analyst Upside", 0.0, 3.0, float(str(s("screener_w_upside", "1.0"))), 0.5)
w_div = sw5.slider("Div Yield", 0.0, 3.0, float(str(s("screener_w_div_yield", "1.0"))), 0.5)

if st.button("Save Screener Weights"):
    set_setting("screener_w_pe", str(w_pe))
    set_setting("screener_w_growth", str(w_growth))
    set_setting("screener_w_momentum", str(w_momentum))
    set_setting("screener_w_upside", str(w_upside))
    set_setting("screener_w_div_yield", str(w_div))
    st.success("Screener weights saved.")

st.divider()

# ── Portfolio settings ────────────────────────────────────────────────────────

st.subheader("Portfolio Settings")

col3, col4 = st.columns(2)

with col3:
    concentration_pct = st.number_input(
        "Concentration warning threshold %",
        min_value=5.0, max_value=100.0,
        value=float(str(s("concentration_pct", "25.0"))),
        step=1.0, format="%.1f",
    )
    st.caption("Allocation page warns if any single holding exceeds this % of portfolio value.")

with col4:
    sharpe_rf_rate = st.number_input(
        "Sharpe ratio risk-free rate %",
        min_value=0.0, max_value=20.0,
        value=float(str(s("sharpe_rf_rate", "4.0"))),
        step=0.25, format="%.2f",
    )
    st.caption("Used in Analytics page Sharpe ratio calculation.")

if st.button("Save Portfolio Settings"):
    set_setting("concentration_pct", str(concentration_pct))
    set_setting("sharpe_rf_rate", str(sharpe_rf_rate))
    st.success("Portfolio settings saved.")

st.divider()

# ── CSV import info ───────────────────────────────────────────────────────────

st.subheader("CSV Import")

last_import = s("last_csv_import", None)
if last_import:
    st.info(f"Last CSV import: **{last_import}**")
else:
    st.caption("No CSV import on record yet.")

weekly_reminder = st.toggle(
    "Weekly import reminder",
    value=s("csv_weekly_reminder", "0") == "1",
)
if st.button("Save CSV Settings"):
    set_setting("csv_weekly_reminder", "1" if weekly_reminder else "0")
    st.success("CSV settings saved.")

# Show weekly reminder banner if enabled and it's been 7+ days
if last_import and s("csv_weekly_reminder", "0") == "1":
    from datetime import datetime, timedelta
    try:
        last_dt = datetime.strptime(last_import, "%Y-%m-%d")
        if datetime.now() - last_dt >= timedelta(days=7):
            st.warning("⏰ It's been 7+ days since your last CSV import. Consider importing a fresh export.")
    except ValueError:
        pass

st.divider()

# ── Clear all data ────────────────────────────────────────────────────────────

st.subheader("Clear All Data")
st.caption("⚠️ This permanently deletes all transactions, watchlist items, notifications, and screener configs.")

if st.button("Clear All Data", type="primary"):
    st.session_state["confirm_clear_data"] = True

if st.session_state.get("confirm_clear_data"):
    st.error("This cannot be undone. Are you absolutely sure?")
    cc1, cc2 = st.columns([1, 5])
    if cc1.button("Yes, clear everything"):
        from database import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM transactions")
        conn.execute("DELETE FROM watchlist")
        conn.execute("DELETE FROM notifications")
        conn.execute("DELETE FROM screener_configs")
        conn.execute("DELETE FROM settings")
        conn.commit()
        conn.close()
        st.session_state.pop("confirm_clear_data", None)
        st.success("All data cleared.")
        st.rerun()
    if cc2.button("Cancel"):
        st.session_state.pop("confirm_clear_data", None)
        st.rerun()