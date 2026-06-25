import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from database import initialize_db, get_transactions, get_watchlist
from data import get_earnings_dates

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Earnings", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Earnings")

# ── Build ticker list from holdings + watchlist ───────────────────────────────

def get_held_tickers(transactions):
    by_ticker = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    held = []
    for ticker, txs in by_ticker.items():
        shares = 0.0
        for tx in txs:
            if tx["type"] == "buy":
                shares += tx["shares"]
            elif tx["type"] == "sell":
                shares -= tx["shares"]
        if shares > 0.0001:
            held.append(ticker)
    return held


transactions = get_transactions()
held_tickers = get_held_tickers(transactions)
watchlist = get_watchlist()
watch_tickers = [w["ticker"] for w in watchlist]

# Combine, deduplicate, held first
all_tickers = list(dict.fromkeys(held_tickers + watch_tickers))

if not all_tickers:
    st.info("No holdings or watchlist tickers yet.")
    st.stop()

# ── Fetch earnings dates for all tickers ──────────────────────────────────────

with st.spinner("Loading earnings data..."):
    all_rows = []
    for ticker in all_tickers:
        df = get_earnings_dates(ticker, limit=8)
        if df.empty:
            continue
        df = df.reset_index()

        # yfinance column name for the date index varies — normalise it
        date_col = df.columns[0]
        df = df.rename(columns={
            date_col: "Date",
            "EPS Estimate": "EPS Estimate",
            "Reported EPS": "Reported EPS",
            "Surprise(%)": "Surprise %",
        })

        df["Ticker"] = ticker
        df["Source"] = "Portfolio" if ticker in held_tickers else "Watchlist"
        all_rows.append(df)

if not all_rows:
    st.warning("No earnings data found for any tickers.")
    st.stop()

earnings_df = pd.concat(all_rows, ignore_index=True)

# Ensure Date column is tz-naive datetime
earnings_df["Date"] = pd.to_datetime(earnings_df["Date"]).dt.tz_localize(None)

now = pd.Timestamp.now()

# Split into upcoming and past
upcoming_df = earnings_df[earnings_df["Date"] >= now].copy()
past_df = earnings_df[earnings_df["Date"] <  now].copy()

# ── Earnings this week flag ───────────────────────────────────────────────────

week_end = now + timedelta(days=7)
this_week = upcoming_df[upcoming_df["Date"] <= week_end]

if not this_week.empty:
    st.warning("📅 **Earnings this week:**")
    for _, row in this_week.iterrows():
        eps_est = f" | EPS Estimate: ${row['EPS Estimate']:.2f}" if pd.notna(row.get("EPS Estimate")) else ""
        st.warning(f"  • **{row['Ticker']}** — {pd.Timestamp(row['Date']).strftime('%Y-%m-%d')}{eps_est}")
else:
    st.success("✅ No earnings in the next 7 days.")

st.divider()

# ── Upcoming earnings ─────────────────────────────────────────────────────────

st.subheader("Upcoming Earnings")

if upcoming_df.empty:
    st.caption("No upcoming earnings dates found.")
else:
    upcoming_display = upcoming_df[["Date", "Ticker", "Source", "EPS Estimate"]].copy()
    upcoming_display = upcoming_display.sort_values("Date")
    upcoming_display["Date"] = upcoming_display["Date"].dt.strftime("%Y-%m-%d")
    upcoming_display["EPS Estimate"] = upcoming_display["EPS Estimate"].apply(
        lambda x: f"${x:.2f}" if pd.notna(x) else "N/A"
    )
    st.dataframe(upcoming_display, use_container_width=True, hide_index=True)

st.divider()

# ── Past earnings + surprise % ────────────────────────────────────────────────

st.subheader("Past Earnings")
st.caption("Surprise % = how much reported EPS differed from the estimate. Positive = beat, negative = miss.")

if past_df.empty:
    st.caption("No past earnings data found.")
else:
    past_display = past_df[["Date", "Ticker", "Source", "EPS Estimate", "Reported EPS", "Surprise %"]].copy()
    past_display = past_display.sort_values("Date", ascending=False)
    past_display["Date"] = past_display["Date"].dt.strftime("%Y-%m-%d")

    # Format numeric columns
    for col in ["EPS Estimate", "Reported EPS"]:
        past_display[col] = past_display[col].apply(
            lambda x: f"${x:.2f}" if pd.notna(x) else "N/A"
        )
    past_display["Surprise %"] = past_display["Surprise %"].apply(
        lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A"
    )

    # Color surprise % green/red
    def color_surprise(val):
        if val == "N/A":
            return ""
        try:
            num = float(val.replace("%", ""))
            return "color: green" if num >= 0 else "color: red"
        except ValueError:
            return ""

    styled = past_display.style.map(color_surprise, subset=["Surprise %"])  # type: ignore
    st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ── Per-ticker detail ─────────────────────────────────────────────────────────

st.subheader("Per-Ticker Earnings History")

selected = st.selectbox("Select ticker", sorted(all_tickers))
ticker_earnings = earnings_df[earnings_df["Ticker"] == selected].copy()

if ticker_earnings.empty:
    st.caption(f"No earnings data found for {selected}.")
else:
    ticker_earnings = ticker_earnings.sort_values("Date", ascending=False)
    ticker_earnings["Date"] = ticker_earnings["Date"].dt.strftime("%Y-%m-%d")

    for col in ["EPS Estimate", "Reported EPS"]:
        if col in ticker_earnings.columns:
            ticker_earnings[col] = ticker_earnings[col].apply(
                lambda x: f"${x:.2f}" if pd.notna(x) else "N/A"
            )
    if "Surprise %" in ticker_earnings.columns:
        ticker_earnings["Surprise %"] = ticker_earnings["Surprise %"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A"
        )

    st.dataframe(
        ticker_earnings[["Date", "EPS Estimate", "Reported EPS", "Surprise %"]],
        use_container_width=True,
        hide_index=True,
    )