import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from database import initialize_db, get_transactions
from data import get_price_history, get_bulk_current_prices
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

from utils.theme import apply_theme
apply_theme()

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
        for tx in txs:
            if tx["type"] == "buy":
                cost_basis += tx["shares"] * tx["price"]
                shares_held += tx["shares"]
            elif tx["type"] == "sell" and shares_held > 0:
                avg = cost_basis / shares_held
                sell = min(tx["shares"], shares_held)
                cost_basis -= sell * avg
                shares_held -= sell
        if shares_held > 0.0001:
            holdings.append({"ticker": ticker, "shares": shares_held, "cost_basis": cost_basis})

    return holdings


transactions = get_transactions()
holdings = compute_holdings(transactions)

if not holdings:
    st.info("No holdings yet — add transactions on the Portfolio page.")
    st.stop()

tickers = [h["ticker"] for h in holdings]

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

portfolio_value_series = calculate_portfolio_value_over_time(transactions, price_history)

if portfolio_value_series.empty:
    st.warning("Not enough price history to calculate portfolio performance.")
    st.stop()

# ── Summary metrics ────────────────────────────────────────────────────────────

total_return = calculate_total_return(portfolio_value_series)
annualized_return = calculate_annualized_return(portfolio_value_series)
returns = calculate_returns(portfolio_value_series)
from database import get_setting
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

performance_rows = []
for t in tickers:
    if t in price_history and not price_history[t].empty:
        ret = calculate_total_return(price_history[t])
        performance_rows.append({"Ticker": t, "Return %": round(ret, 2)})

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
    fig_bar.update_layout(margin=dict(
        t=40, b=0, l=0, r=0), 
        coloraxis_showscale=False, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_bar, use_container_width=True)