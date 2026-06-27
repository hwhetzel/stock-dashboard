import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from database import initialize_db, get_transactions, get_setting, get_known_accounts, get_portfolio_snapshots, get_snapshot_count
from data import get_price_history, get_bulk_current_prices, get_company_names
from utils.metrics import (
    calculate_returns,
    calculate_total_return,
    calculate_annualized_return,
    calculate_sharpe_ratio,
    calculate_portfolio_value_over_time,
    normalize_to_100,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Analytics", layout="wide")
initialize_db()

from utils.theme import apply_theme, show_notification_badge
apply_theme()
show_notification_badge()

st.title("Analytics")


# ── Rebuild holdings ───────────────────────────────────────────────────────────

def compute_holdings(transactions):
    by_ticker = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    holdings = []
    for ticker, txs in by_ticker.items():
        shares_held = 0.0
        cost_basis = 0.0
        accounts = set()
        for tx in txs:
            if tx.get("account"):
                accounts.add(tx["account"])
            if tx["type"] == "buy":
                cost_basis += tx["shares"] * tx["price"]
                shares_held += tx["shares"]
            elif tx["type"] == "sell" and shares_held > 0:
                avg = cost_basis / shares_held
                sell = min(tx["shares"], shares_held)
                cost_basis -= sell * avg
                shares_held -= sell
        if shares_held > 0.0001:
            holdings.append({
                "ticker": ticker,
                "shares": shares_held,
                "cost_basis": cost_basis,
                "accounts": ", ".join(sorted(accounts)) if accounts else "",
            })
    return holdings


transactions = get_transactions()
holdings = compute_holdings(transactions)

from datetime import date as dt
today = dt.today().strftime("%Y-%m-%d")
csv_transactions = [t for t in transactions if t.get("source") == "csv_import"]

if csv_transactions:
    multi_date_count = sum(1 for t in csv_transactions if t["date"] == today)
    if multi_date_count > 0:
        st.warning(
            f"⚠️ **{multi_date_count} imported position(s)** have today as their open date — "
            f"this happens when Ameriprise reports 'Multiple' open dates for a position. "
            f"Total return, annualized return, and Sharpe ratio will not be accurate for these positions. "
            f"To fix, go to **Portfolio → Edit / Delete a Transaction** and update the date "
            f"to your actual purchase date for each affected position."
        )
    else:
        st.info(
            "ℹ️ Returns are calculated from your transaction dates. "
            "If any dates are incorrect, update them on the Portfolio page."
        )

if not holdings:
    st.info("No holdings yet — add transactions on the Portfolio page.")
    st.stop()

tickers = [h["ticker"] for h in holdings]
names = get_company_names(tickers)

# ── Period selector ────────────────────────────────────────────────────────────

PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "2 Years": "2y",
    "5 Years": "5y",
    "Max": "max",
}

selected_label = st.selectbox("Period", list(PERIOD_OPTIONS.keys()), index=3)
period = PERIOD_OPTIONS[selected_label]

st.divider()

# ── Fetch price history for all holdings + SPY benchmark ─────────────────────

with st.spinner("Loading price history..."):
    price_history = {}
    for t in tickers:
        hist = get_price_history(t, period=period, interval="1d")
        if not hist.empty and "Close" in hist.columns:
            series = hist["Close"]
            # Strip timezone so all comparisons are tz-naive
            series.index = series.index.tz_localize(None) if series.index.tz is None else series.index.tz_convert(None) # type: ignore
            price_history[t] = series

    spy_hist = get_price_history("SPY", period=period, interval="1d")
    if not spy_hist.empty:
        spy_close = spy_hist["Close"]
        spy_close.index = spy_close.index.tz_localize(None) if spy_close.index.tz is None else spy_close.index.tz_convert(None) # type: ignore
    else:
        spy_close = pd.Series(dtype=float)

# ── Portfolio value over time ─────────────────────────────────────────────────
# Prefer real snapshots if we have 5+ days of data — these are accurate
# regardless of whether transaction dates are correct. Fall back to the
# reconstructed method (calculate_portfolio_value_over_time) when snapshots
# are too sparse to be useful.

snapshots = get_portfolio_snapshots()
SNAPSHOT_THRESHOLD = 5  # days of snapshots needed before we trust them

if len(snapshots) >= SNAPSHOT_THRESHOLD:
    # Build series from real observed daily values
    snap_df = pd.DataFrame(snapshots)
    snap_df["date"] = pd.to_datetime(snap_df["date"])
    snap_df = snap_df.set_index("date").sort_index()

    # Apply period filter to match the selected period selector
    if period != "max":
        period_map = {
            "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825,
        }
        days = period_map.get(period, 365)
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=days)
        snap_df = snap_df[snap_df.index >= cutoff]

    portfolio_value_series = snap_df["value"]
    using_snapshots = True
else:
    # Not enough snapshots yet — fall back to reconstructed method
    portfolio_value_series = calculate_portfolio_value_over_time(transactions, price_history)
    using_snapshots = False

if portfolio_value_series.empty:
    st.warning("Not enough price history to calculate portfolio performance.")
    st.stop()

# Show a one-time info message explaining which method is being used
if using_snapshots:
    remaining = 0
    st.caption(
        f"✅ Using {len(snapshots)} days of real portfolio snapshots for return calculations. "
        f"Accuracy improves as more daily snapshots accumulate."
    )
else:
    remaining = SNAPSHOT_THRESHOLD - len(snapshots)
    st.caption(
        f"⏳ Collecting daily snapshots ({len(snapshots)}/{SNAPSHOT_THRESHOLD} days so far). "
        f"Returns are reconstructed from transaction history until {remaining} more day(s) of data are saved."
    )

# ── Summary metrics ────────────────────────────────────────────────────────────

total_return = calculate_total_return(portfolio_value_series)
annualized_return = calculate_annualized_return(portfolio_value_series)
returns = calculate_returns(portfolio_value_series)

rf_rate = float(str(get_setting("sharpe_rf_rate", "4.0"))) / 100
sharpe = calculate_sharpe_ratio(returns, risk_free_rate=rf_rate)

spy_total_return = calculate_total_return(spy_close) if not spy_close.empty else None

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Total Return ({selected_label})", f"{total_return:.2f}%")
c2.metric("Annualized Return", f"{annualized_return:.2f}%")
c3.metric("Sharpe Ratio", f"{sharpe:.2f}")
if spy_total_return is not None:
    diff = total_return - spy_total_return
    c4.metric(
        "vs S&P 500",
        f"{spy_total_return:.2f}%",
        delta=f"{diff:+.2f}% pts",
    )

st.caption("Sharpe Ratio uses a 4% annual risk-free rate assumption — update in utils/metrics.py if desired.")

st.divider()

# ── Benchmark comparison chart ─────────────────────────────────────────────────

st.subheader(f"Portfolio vs S&P 500 ({selected_label})")

fig = go.Figure()

normalized_portfolio = normalize_to_100(portfolio_value_series)
fig.add_trace(go.Scatter(
    x=normalized_portfolio.index,
    y=normalized_portfolio.values,
    name="Your Portfolio",
    line=dict(width=2.5),
))

if not spy_close.empty:
    normalized_spy = normalize_to_100(spy_close)
    fig.add_trace(go.Scatter(
        x=normalized_spy.index,
        y=normalized_spy.values,
        name="S&P 500 (SPY)",
        line=dict(width=2, dash="dot"),
    ))

fig.update_layout(
    yaxis_title="Indexed Value (start = 100)",
    xaxis_title="Date",
    hovermode="x unified",
    margin=dict(t=20, b=0, l=0, r=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Best / worst performers ────────────────────────────────────────────────────

st.subheader("Best & Worst Performers")

# Determine if Account column should show
show_account_col = (
    get_setting("has_multiple_accounts", "false") == "true"
    or len(get_known_accounts()) > 1
)

# Build account lookup from holdings
account_map = {h["ticker"]: h.get("accounts", "") for h in holdings}

performance_rows = []
for t in tickers:
    if t in price_history and not price_history[t].empty:
        ret = calculate_total_return(price_history[t])
        row = {"Ticker": t, "Company": names.get(t, t), "Return %": round(ret, 2)}
        if show_account_col:
            row["Account"] = account_map.get(t, "")
        performance_rows.append(row)

if performance_rows:
    perf_df = pd.DataFrame(performance_rows).sort_values("Return %", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🏆 Best Performers**")
        st.dataframe(perf_df.head(3), use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**📉 Worst Performers**")
        st.dataframe(perf_df.tail(3).sort_values("Return %"), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**All Holdings — Return Comparison**")
    import plotly.express as px
    fig_bar = px.bar(
        perf_df, x="Ticker", y="Return %",
        color="Return %", color_continuous_scale="RdYlGn",
        title=f"Return by Holding ({selected_label})",
    )
    fig_bar.update_layout(
        margin=dict(t=40, b=0, l=0, r=0),
        coloraxis_showscale=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig_bar, use_container_width=True)