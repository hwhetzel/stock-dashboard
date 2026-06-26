import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import initialize_db, get_transactions
from data import get_dividends, get_dividend_calendar, get_bulk_current_prices

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Dividends", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

from utils.price_monitor import run_idle_monitor
run_idle_monitor()

st.title("Dividends")

# ── Rebuild holdings from transactions ────────────────────────────────────────

def compute_holdings(transactions):
    by_ticker = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    holdings = []
    for ticker, txs in by_ticker.items():
        shares_held = 0.0
        cost_basis  = 0.0
        for tx in txs:
            if tx["type"] == "buy":
                cost_basis  += tx["shares"] * tx["price"]
                shares_held += tx["shares"]
            elif tx["type"] == "sell" and shares_held > 0:
                avg  = cost_basis / shares_held
                sell = min(tx["shares"], shares_held)
                cost_basis  -= sell * avg
                shares_held -= sell
        if shares_held > 0.0001:
            holdings.append({"ticker": ticker, "shares": shares_held})

    return holdings


transactions = get_transactions()
holdings = compute_holdings(transactions)

if not holdings:
    st.info("No holdings yet — add transactions on the Portfolio page.")
    st.stop()

tickers = [h["ticker"] for h in holdings]
prices = get_bulk_current_prices(tickers)

# ── Per-holding dividend data ──────────────────────────────────────────────────
# Build a combined record: dividend history, annual income, yield, ex-div date

dividend_data = []        # for summary table
all_payments = []        # for income-over-time chart (one row per payment)

for h in holdings:
    ticker = h["ticker"]
    shares = h["shares"]

    div_history = get_dividends(ticker)          # Series: date -> per-share amount
    calendar = get_dividend_calendar(ticker)   # dict: ex_dividend_date, dividend_rate, etc.

    # Annual income estimate = current dividend rate * shares held
    annual_rate  = calendar.get("dividend_rate") or 0
    annual_income = annual_rate * shares
    div_yield = calendar.get("dividend_yield")
    price = prices.get(ticker)

    # Format ex-dividend date (yfinance returns a unix timestamp or None)
    ex_date_raw = calendar.get("ex_dividend_date")
    ex_date_str = "N/A"
    if ex_date_raw:
        try:
            ex_date_str = datetime.fromtimestamp(ex_date_raw).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            ex_date_str = "N/A"

    dividend_data.append({
        "Ticker": ticker,
        "Shares": round(shares, 4),
        "Annual Rate/Share": annual_rate,
        "Est. Annual Income": round(annual_income, 2),
        "Yield": div_yield,
        "Next Ex-Div Date": ex_date_str,
    })

    # Build payment history rows (amount received = per-share div * shares held at that time)
    # NOTE: we use *current* shares held as an approximation since historical
    # share count changes aren't tracked per dividend date — good enough for
    # a personal dashboard, flagged in the caption below.
    if not div_history.empty:
        for pay_date, per_share in div_history.items():
            all_payments.append({
                "Date": pay_date,
                "Ticker": ticker,
                "Amount": per_share * shares,
            })

div_df = pd.DataFrame(dividend_data)

# ── Summary metrics ────────────────────────────────────────────────────────────

total_annual_income = div_df["Est. Annual Income"].sum()
total_portfolio_value = sum(
    h["shares"] * prices.get(h["ticker"], 0) for h in holdings
)
portfolio_yield = (
    (total_annual_income / total_portfolio_value * 100) if total_portfolio_value else 0
)

c1, c2, c3 = st.columns(3)
c1.metric("Est. Annual Dividend Income", f"${total_annual_income:,.2f}")
c2.metric("Portfolio Dividend Yield", f"{portfolio_yield:.2f}%")
c3.metric("Dividend-Paying Holdings", int((div_df["Annual Rate/Share"] > 0).sum()))

st.divider()

# ── Per-holding table ──────────────────────────────────────────────────────────

st.subheader("Dividend Income by Holding")

display_df = div_df.copy()
display_df["Yield"] = display_df["Yield"].apply(
    lambda y: f"{y*100:.2f}%" if pd.notna(y) and y else "N/A"
)
display_df["Annual Rate/Share"] = display_df["Annual Rate/Share"].map("${:.4f}".format)
display_df["Est. Annual Income"] = display_df["Est. Annual Income"].map("${:,.2f}".format)
display_df = display_df.sort_values("Est. Annual Income", ascending=False)

st.dataframe(display_df, use_container_width=True, hide_index=True)

st.caption(
    "Annual income is estimated using the most recent dividend rate × current shares held. "
    "Past payment amounts below use current share count as an approximation."
)

st.divider()

# ── Upcoming ex-dividend dates ─────────────────────────────────────────────────

st.subheader("Upcoming Ex-Dividend Dates")

upcoming = div_df[div_df["Next Ex-Div Date"] != "N/A"].copy()
if upcoming.empty:
    st.caption("No upcoming ex-dividend dates found.")
else:
    upcoming["_sort"] = pd.to_datetime(upcoming["Next Ex-Div Date"])
    upcoming = upcoming.sort_values("_sort").drop(columns="_sort")
    st.dataframe(
        upcoming[["Ticker", "Next Ex-Div Date", "Annual Rate/Share"]],
        use_container_width=True,
        hide_index=True,
    )

st.divider()

# ── Payment history ────────────────────────────────────────────────────────────

st.subheader("Payment History")

if not all_payments:
    st.caption("No dividend payment history found for current holdings.")
else:
    payments_df = pd.DataFrame(all_payments)
    payments_df["Date"] = pd.to_datetime(payments_df["Date"]).dt.tz_localize(None)
    payments_df = payments_df.sort_values("Date", ascending=False)

    # Filter to last 5 years to keep the table manageable
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=5)
    payments_df = payments_df[payments_df["Date"] >= cutoff]

    display_payments = payments_df.copy()
    display_payments["Date"] = display_payments["Date"].dt.strftime("%Y-%m-%d")
    display_payments["Amount"] = display_payments["Amount"].map("${:.2f}".format)

    st.dataframe(display_payments, use_container_width=True, hide_index=True)

    st.divider()

    # ── Income over time chart ────────────────────────────────────────────────

    st.subheader("Income Over Time")

    period_choice = st.radio(
        "Group by", ["Month", "Quarter", "Year"], horizontal=True, index=2
    )

    freq_map = {"Month": "ME", "Quarter": "QE", "Year": "YE"}
    grouped = (
        payments_df.set_index("Date")
        .groupby([pd.Grouper(freq=freq_map[period_choice]), "Ticker"])["Amount"]
        .sum()
        .reset_index()
    )

    fig = px.bar(
        grouped,
        x="Date",
        y="Amount",
        color="Ticker",
        title=f"Dividend Income by {period_choice}",
        labels={"Amount": "Income ($)"},
    )
    fig.update_layout(margin=dict(
        t=40, b=0, l=0, r=0), 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)