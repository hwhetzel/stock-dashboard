import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.figure_factory as ff
import numpy as np
from database import initialize_db, get_transactions
from data import get_bulk_current_prices, get_bulk_ticker_info, get_price_history

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Allocation", layout="wide")
initialize_db()

st.title("Allocation")

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
            holdings.append({"ticker": ticker, "shares": shares_held, "cost_basis": cost_basis})

    return holdings


transactions = get_transactions()
holdings     = compute_holdings(transactions)

if not holdings:
    st.info("No holdings yet — add transactions on the Portfolio page.")
    st.stop()

# ── Fetch live prices and sector info ─────────────────────────────────────────

tickers      = [h["ticker"] for h in holdings]
prices       = get_bulk_current_prices(tickers)
info_map     = get_bulk_ticker_info(tickers)

# Build a flat DataFrame with market value and sector per holding
rows = []
for h in holdings:
    t       = h["ticker"]
    price   = prices.get(t, 0)
    mkt_val = h["shares"] * price
    sector  = info_map.get(t, {}).get("sector", "Unknown")
    rows.append({"Ticker": t, "Market Value": mkt_val, "Sector": sector})

df = pd.DataFrame(rows)
total_value = df["Market Value"].sum()
df["Weight %"] = (df["Market Value"] / total_value * 100).round(2)

# ── Concentration warning ─────────────────────────────────────────────────────

CONCENTRATION_THRESHOLD = 25.0   # warn if any single holding exceeds this %

concentrated = df[df["Weight %"] > CONCENTRATION_THRESHOLD]
if not concentrated.empty:
    for _, row in concentrated.iterrows():
        st.warning(
            f"⚠️ **{row['Ticker']}** represents **{row['Weight %']:.1f}%** of your portfolio "
            f"— above the {CONCENTRATION_THRESHOLD:.0f}% concentration threshold."
        )

st.divider()

# ── Allocation by ticker ──────────────────────────────────────────────────────

st.subheader("Allocation by Ticker")

col1, col2 = st.columns([1, 1])

with col1:
    fig_ticker = px.pie(
        df,
        names="Ticker",
        values="Market Value",
        hole=0.45,           # donut style
        title="By Ticker",
    )
    fig_ticker.update_traces(textposition="inside", textinfo="percent+label")
    fig_ticker.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
    st.plotly_chart(fig_ticker, use_container_width=True)

with col2:
    # Ticker weight table alongside the chart
    display_df = df[["Ticker", "Market Value", "Weight %", "Sector"]].copy()
    display_df["Market Value"] = display_df["Market Value"].map("${:,.2f}".format)
    display_df["Weight %"]     = display_df["Weight %"].map("{:.2f}%".format)
    display_df = display_df.sort_values("Weight %", ascending=False)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

st.divider()

# ── Allocation by sector ──────────────────────────────────────────────────────

st.subheader("Allocation by Sector")

sector_df = (
    df.groupby("Sector")["Market Value"]
    .sum()
    .reset_index()
)
sector_df["Weight %"] = (sector_df["Market Value"] / total_value * 100).round(2)

col3, col4 = st.columns([1, 1])

with col3:
    fig_sector = px.pie(
        sector_df,
        names="Sector",
        values="Market Value",
        hole=0.45,
        title="By Sector",
    )
    fig_sector.update_traces(textposition="inside", textinfo="percent+label")
    fig_sector.update_layout(showlegend=False, margin=dict(t=40, b=0, l=0, r=0))
    st.plotly_chart(fig_sector, use_container_width=True)

with col4:
    sector_display = sector_df.copy()
    sector_display["Market Value"] = sector_display["Market Value"].map("${:,.2f}".format)
    sector_display["Weight %"]     = sector_display["Weight %"].map("{:.2f}%".format)
    sector_display = sector_display.sort_values("Weight %", ascending=False)
    st.dataframe(sector_display, use_container_width=True, hide_index=True)

st.divider()

# ── Correlation matrix ────────────────────────────────────────────────────────

st.subheader("Correlation Matrix")
st.caption("Based on daily returns over the past year. Helps identify how closely holdings move together.")

if len(tickers) < 2:
    st.info("Add at least 2 holdings to see a correlation matrix.")
else:
    # Fetch 1y daily close for each ticker and compute pairwise correlation
    price_series = {}
    for t in tickers:
        hist = get_price_history(t, period="1y", interval="1d")
        if not hist.empty and "Close" in hist.columns:
            price_series[t] = hist["Close"]

    if len(price_series) >= 2:
        prices_df   = pd.DataFrame(price_series).dropna()
        returns_df  = prices_df.pct_change().dropna()
        corr_matrix = returns_df.corr().round(2)

        # Plotly annotated heatmap
        fig_corr = px.imshow(
            corr_matrix,
            text_auto=True,
            color_continuous_scale="RdYlGn",  # red = negative, green = positive
            zmin=-1, zmax=1,
            title="Return Correlation (1Y Daily)",
            aspect="auto",
        )
        fig_corr.update_layout(margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.info("Not enough price history to compute correlations.")