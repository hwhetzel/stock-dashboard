import streamlit as st
import pandas as pd
from datetime import date
from database import initialize_db, get_watchlist, add_to_watchlist, remove_from_watchlist, update_watchlist_item, add_transaction
from data import get_bulk_current_prices, get_ticker_info, get_price_history, get_52_week_range, is_valid_ticker
from utils.indicators import compute_rsi, compute_macd, compute_moving_averages

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Watchlist", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Watchlist")

# ── Technical signal helpers ──────────────────────────────────────────────────

def get_signals(ticker: str) -> list[dict]:
    """
    Run technical checks on a ticker and return a list of signal dicts.
    Each dict has: { label, flag, reason }
    flag is one of: "bullish", "bearish", "neutral"
    """
    from database import get_setting
    rsi_overbought = int(str(get_setting("notify_rsi_overbought", "70")))
    rsi_oversold = int(str(get_setting("notify_rsi_oversold", "30")))
    signals = []
    hist = get_price_history(ticker, period="1y", interval="1d")

    if hist.empty or "Close" not in hist.columns:
        return signals

    close = hist["Close"]

    # ── MA crossover (50 vs 200 day) ─────────────────────────────────────────
    mas = compute_moving_averages(close, windows=[50, 200])
    if "MA_50" in mas.columns and "MA_200" in mas.columns:
        ma50  = mas["MA_50"].iloc[-1]
        ma200 = mas["MA_200"].iloc[-1]
        if pd.notna(ma50) and pd.notna(ma200):
            if ma50 > ma200:
                signals.append({
                    "label": "MA Crossover",
                    "flag": "bullish",
                    "reason": f"50-day MA (${ma50:.2f}) is above 200-day MA (${ma200:.2f}) — golden cross territory.",
                })
            else:
                signals.append({
                    "label": "MA Crossover",
                    "flag": "bearish",
                    "reason": f"50-day MA (${ma50:.2f}) is below 200-day MA (${ma200:.2f}) — death cross territory.",
                })

    # ── RSI overbought / oversold ─────────────────────────────────────────────
    rsi_series = compute_rsi(close, period=14)
    if not rsi_series.empty:
        rsi_val = rsi_series.iloc[-1]
        if pd.notna(rsi_val):
            if rsi_val >= rsi_overbought:
                signals.append({
                    "label": "RSI",
                    "flag": "bearish",
                    "reason": f"RSI is {rsi_val:.1f} — overbought (≥{rsi_overbought}). Potential pullback ahead.",
                })
            elif rsi_val <= rsi_oversold:
                signals.append({
                    "label": "RSI",
                    "flag": "bullish",
                    "reason": f"RSI is {rsi_val:.1f} — oversold (≤{rsi_oversold}). Potential bounce ahead.",
                })
            else:
                signals.append({
                    "label": "RSI",
                    "flag": "neutral",
                    "reason": f"RSI is {rsi_val:.1f} — neutral range.",
                })

    # ── 52-week high / low proximity (within 5%) ──────────────────────────────
    week52 = get_52_week_range(ticker)
    current_price = close.iloc[-1]
    high52 = week52.get("high")
    low52  = week52.get("low")

    if high52 and current_price >= high52 * 0.95:
        signals.append({
            "label": "52W High",
            "flag": "bullish",
            "reason": f"Within 5% of 52-week high (${high52:.2f}). Strong momentum.",
        })
    if low52 and current_price <= low52 * 1.05:
        signals.append({
            "label": "52W Low",
            "flag": "bearish",
            "reason": f"Within 5% of 52-week low (${low52:.2f}). Significant weakness.",
        })

    return signals


FLAG_COLORS = {
    "bullish": "🟢",
    "bearish": "🔴",
    "neutral": "🟡",
}

# ── Load watchlist ────────────────────────────────────────────────────────────

watchlist = get_watchlist()
tickers = [w["ticker"] for w in watchlist]
prices = get_bulk_current_prices(tickers) if tickers else {}

# ── Watchlist table ───────────────────────────────────────────────────────────

if not watchlist:
    st.info("Your watchlist is empty. Add a ticker below.")
else:
    st.subheader("Watchlist")

    for item in watchlist:
        ticker  = item["ticker"]
        target_price = item["target_price"]
        current  = prices.get(ticker)

        with st.expander(
            f"**{ticker}** — "
            + (f"${current:,.2f}" if current else "Price unavailable")
            + (f"  |  Target: ${target_price:,.2f}" if target_price else ""),
            expanded=False,
        ):
            col1, col2 = st.columns([3, 1])

            with col1:
                # Target price alert
                if target_price and current:
                    if current >= target_price:
                        st.success(f"✅ Price ${current:.2f} has reached target ${target_price:.2f}")
                    else:
                        pct_away = ((target_price - current) / current) * 100
                        st.info(f"📍 ${pct_away:.1f}% away from target ${target_price:.2f}")

                # Notes
                if item["notes"]:
                    st.caption(f"Notes: {item['notes']}")

                # Technical signals — only load when expander is open
                st.markdown("**Technical Signals**")
                load_signals = st.button("Load Signals", key=f"load_{ticker}")
                if load_signals:
                    with st.spinner("Analysing signals..."):
                        signals = get_signals(ticker)

                if load_signals:
                    if not signals:
                        st.caption("No signals available.")
                    else:
                        for sig in signals:
                            icon = FLAG_COLORS.get(sig["flag"], "⚪")
                            st.markdown(f"{icon} **{sig['label']}** — {sig['reason']}")

            with col2:
                st.markdown("**Actions**")

                # Move to portfolio
                st.caption("Move to Portfolio")
                mv_shares = st.number_input("Shares", min_value=0.001, step=0.01, format="%.4f", key=f"mv_shares_{ticker}")
                mv_price  = st.number_input("Price",  min_value=0.01,  step=0.01, format="%.2f",
                                            value=float(current) if current else 1.0, key=f"mv_price_{ticker}")
                mv_date   = st.date_input("Date", value=date.today(), key=f"mv_date_{ticker}")
                if st.button("Add as Buy", key=f"buy_{ticker}"):
                    if mv_shares <= 0.001:
                        st.error("Enter a share amount greater than 0.001.")
                    else:
                        add_transaction(
                            ticker=ticker,
                            type_="buy",
                            shares=mv_shares,
                            price=mv_price,
                            date=mv_date.strftime("%Y-%m-%d"),
                            notes="Added from watchlist",
                        )
                        remove_from_watchlist(ticker)
                        st.success(f"{ticker} moved to portfolio.")
                        st.rerun()

                st.divider()

                # Edit target / notes
                st.caption("Edit")
                new_target = st.number_input(
                    "Target Price",
                    min_value=0.0,
                    value=float(target_price) if target_price else 0.0,
                    step=0.01, format="%.2f",
                    key=f"target_{ticker}",
                )
                new_notes = st.text_input("Notes", value=item["notes"] or "", key=f"notes_{ticker}")
                if st.button("Save", key=f"save_{ticker}"):
                    update_watchlist_item(ticker, new_target or None, new_notes)
                    st.success("Updated.")
                    st.rerun()

                st.divider()

                # Remove
                if st.button("🗑 Remove", key=f"remove_{ticker}", type="primary"):
                    remove_from_watchlist(ticker)
                    st.rerun()

st.divider()

# ── Add to watchlist ──────────────────────────────────────────────────────────

st.subheader("Add to Watchlist")

with st.form("add_watchlist_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([2, 1.5, 3])
    new_ticker = col1.text_input("Ticker", placeholder="e.g. TSLA").upper().strip()
    new_target = col2.number_input("Target Price (optional)", min_value=0.0, step=0.01, format="%.2f")
    new_notes  = col3.text_input("Notes (optional)", placeholder="e.g. watching for breakout")

    if st.form_submit_button("Add to Watchlist"):
        if not new_ticker:
            st.error("Ticker is required.")
        elif new_ticker in tickers:
            st.warning(f"{new_ticker} is already on your watchlist.")
        elif not is_valid_ticker(new_ticker):
            st.error(f"Could not find ticker '{new_ticker}'. Check the symbol and try again.")
        else:
            add_to_watchlist(
                ticker=new_ticker,
                target_price=new_target or None,
                notes=new_notes,
            )
            st.success(f"{new_ticker} added to watchlist.")
            st.rerun()