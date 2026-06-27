import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from database import initialize_db, get_transactions, get_watchlist
from data import get_price_history
from utils.indicators import compute_moving_averages, compute_rsi, compute_macd

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Charts", layout="wide")
initialize_db()

from utils.theme import apply_theme, show_notification_badge
apply_theme()
show_notification_badge()

st.title("Charts")

# ── Build ticker list from holdings + watchlist ───────────────────────────────

def get_held_tickers(transactions):
    by_ticker = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    held = []
    for ticker, txs in by_ticker.items():
        shares_held = 0.0
        for tx in txs:
            if tx["type"] == "buy":
                shares_held += tx["shares"]
            elif tx["type"] == "sell":
                shares_held -= tx["shares"]
        if shares_held > 0.0001:
            held.append(ticker)
    return held


transactions = get_transactions()
held_tickers = get_held_tickers(transactions)
watchlist = get_watchlist()
watch_tickers = [w["ticker"] for w in watchlist]

# Combine and deduplicate, held tickers first
all_tickers = list(dict.fromkeys(held_tickers + watch_tickers))

if not all_tickers:
    st.info("No holdings or watchlist tickers yet.")
    st.stop()

# ── Controls ──────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns([2, 2, 2])

with col1:
    selected_ticker = st.selectbox("Ticker", all_tickers)

with col2:
    PERIOD_OPTIONS = {
        "1 Month": "1mo",
        "3 Months": "3mo",
        "6 Months": "6mo",
        "1 Year": "1y",
        "2 Years": "2y",
        "5 Years": "5y",
    }
    selected_period_label = st.selectbox("Period", list(PERIOD_OPTIONS.keys()), index=3)
    selected_period = PERIOD_OPTIONS[selected_period_label]

with col3:
    chart_type = st.selectbox("Chart Type", ["Candlestick", "Line"])

# MA overlays
st.markdown("**Moving Average Overlays**")
ma_col1, ma_col2, ma_col3, ma_col4 = st.columns(4)
show_ma20 = ma_col1.checkbox("MA 20",  value=False)
show_ma50 = ma_col2.checkbox("MA 50",  value=True)
show_ma100 = ma_col3.checkbox("MA 100", value=False)
show_ma200 = ma_col4.checkbox("MA 200", value=True)

# Indicator panels
st.markdown("**Indicator Panels**")
ind_col1, ind_col2 = st.columns(2)
show_rsi = ind_col1.checkbox("RSI (14)", value=True)
show_macd = ind_col2.checkbox("MACD",     value=True)

st.divider()

# ── Fetch data ────────────────────────────────────────────────────────────────

with st.spinner(f"Loading {selected_ticker}..."):
    hist = get_price_history(selected_ticker or "", period=selected_period, interval="1d")

if hist.empty:
    st.error(f"No price data found for {selected_ticker}.")
    st.stop()

# Strip timezone from index for clean plotting
if hist.index.tz is not None: # type: ignore
    hist.index = hist.index.tz_convert(None)  # type: ignore

close = hist["Close"]
open_ = hist["Open"]
high = hist["High"]
low = hist["Low"]
volume = hist["Volume"]

# ── Compute indicators ────────────────────────────────────────────────────────

ma_windows = []
if show_ma20: ma_windows.append(20)
if show_ma50: ma_windows.append(50)
if show_ma100: ma_windows.append(100)
if show_ma200: ma_windows.append(200)

mas = compute_moving_averages(close, windows=ma_windows) if ma_windows else pd.DataFrame()
rsi = compute_rsi(close, period=14)
macd_df = compute_macd(close)

# ── Build subplot layout ──────────────────────────────────────────────────────
# Rows: price (always) + volume (always) + RSI (optional) + MACD (optional)

num_panels = 2 + int(show_rsi) + int(show_macd)
row_heights = [0.55, 0.15]
if show_rsi: row_heights.append(0.15)
if show_macd: row_heights.append(0.15)

subplot_titles = [selected_ticker, "Volume"]
if show_rsi: subplot_titles.append("RSI (14)")
if show_macd: subplot_titles.append("MACD")

fig = make_subplots(
    rows=num_panels,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.04,
    row_heights=row_heights,
    subplot_titles=subplot_titles,
)

# ── Price chart ───────────────────────────────────────────────────────────────

if chart_type == "Candlestick":
    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=open_, high=high, low=low, close=close,
        name=selected_ticker,
        increasing_line_color="green",
        decreasing_line_color="red",
    ), row=1, col=1)
else:
    fig.add_trace(go.Scatter(
        x=hist.index, y=close,
        name=selected_ticker,
        line=dict(width=2),
    ), row=1, col=1)

# MA overlays on price chart
MA_COLORS = {20: "orange", 50: "blue", 100: "purple", 200: "red"}
for window in ma_windows:
    col_name = f"MA_{window}"
    if col_name in mas.columns:
        fig.add_trace(go.Scatter(
            x=mas.index,
            y=mas[col_name],
            name=f"MA {window}",
            line=dict(width=1.2, color=MA_COLORS.get(window, "gray")),
        ), row=1, col=1)

# ── Volume bars ───────────────────────────────────────────────────────────────

# Color volume bars green/red to match price direction
vol_colors = [
    "green" if c >= o else "red"
    for c, o in zip(close, open_)
]
fig.add_trace(go.Bar(
    x=hist.index,
    y=volume,
    name="Volume",
    marker_color=vol_colors,
    showlegend=False,
), row=2, col=1)

# ── RSI panel ─────────────────────────────────────────────────────────────────

if show_rsi:
    rsi_row = 3
    fig.add_trace(go.Scatter(
        x=rsi.index, y=rsi.values,
        name="RSI",
        line=dict(width=1.5, color="purple"),
    ), row=rsi_row, col=1)

    # Overbought / oversold reference lines
    fig.add_hline(y=70, line_dash="dash", line_color="red",   row=rsi_row, col=1)  # type: ignore
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=rsi_row, col=1)  # type: ignore
    fig.update_yaxes(range=[0, 100], row=rsi_row, col=1)

# ── MACD panel ────────────────────────────────────────────────────────────────

if show_macd:
    macd_row = 3 + int(show_rsi)

    fig.add_trace(go.Scatter(
        x=macd_df.index, y=macd_df["MACD"],
        name="MACD",
        line=dict(width=1.5, color="blue"),
    ), row=macd_row, col=1)

    fig.add_trace(go.Scatter(
        x=macd_df.index, y=macd_df["Signal"],
        name="Signal",
        line=dict(width=1.5, color="orange"),
    ), row=macd_row, col=1)

    # Histogram bars colored by positive/negative
    hist_colors = [
        "green" if v >= 0 else "red"
        for v in macd_df["Histogram"]
    ]
    fig.add_trace(go.Bar(
        x=macd_df.index,
        y=macd_df["Histogram"],
        name="Histogram",
        marker_color=hist_colors,
        showlegend=False,
    ), row=macd_row, col=1)

# ── Layout ────────────────────────────────────────────────────────────────────

fig.update_layout(
    height=700 + (150 * (int(show_rsi) + int(show_macd))),
    xaxis_rangeslider_visible=False,   # hide candlestick range slider (clutters layout)
    hovermode="x unified",
    margin=dict(t=40, b=0, l=0, r=0),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
)

st.plotly_chart(fig, use_container_width=True)