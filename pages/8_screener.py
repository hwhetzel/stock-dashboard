import streamlit as st
import pandas as pd
import json
from database import initialize_db, add_to_watchlist, save_screener_config, get_screener_configs, delete_screener_config
from data import get_ticker_info, is_valid_ticker

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Screener", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Stock Screener")

st.caption(
    "⚠️ **Disclaimer:** Scores and rankings are for informational purposes only and do not "
    "constitute financial advice. Always do your own research before making investment decisions."
)

st.divider()

# ── Scoring logic ─────────────────────────────────────────────────────────────

def score_ticker(info: dict, weights: dict) -> dict:
    """
    Score a ticker across up to 5 factors. Each factor is scored 0–100
    then multiplied by its weight. Final score is sum of weighted scores.

    Factors:
    - pe          : lower P/E is better (capped at 0–50 range)
    - growth      : higher earnings growth % is better
    - momentum    : higher 52W price return is better
    - upside      : analyst target price upside % vs current price
    - div_yield   : higher dividend yield is better
    """
    scores = {}
    details = {}

    # ── P/E Score ─────────────────────────────────────────────────────────────
    # Score 100 at P/E=5, score 0 at P/E=50+. Linear in between.
    pe = info.get("trailingPE") or info.get("forwardPE")
    if pe and pe > 0:
        pe_score = max(0, min(100, (50 - pe) / 45 * 100))
        scores["pe"] = pe_score
        details["P/E"] = round(pe, 2)
    else:
        scores["pe"] = 0
        details["P/E"] = "N/A"

    # ── Earnings Growth Score ─────────────────────────────────────────────────
    # Uses earnings quarterly growth YoY. Score 100 at 50%+ growth, 0 at 0% or below.
    growth = info.get("earningsQuarterlyGrowth")
    if growth is not None:
        growth_pct = growth * 100
        growth_score = max(0, min(100, growth_pct * 2))
        scores["growth"] = growth_score
        details["EPS Growth %"] = round(growth_pct, 2)
    else:
        scores["growth"] = 0
        details["EPS Growth %"] = "N/A"

    # ── Momentum Score ────────────────────────────────────────────────────────
    # Uses 52-week price change: (current - 52wLow) / (52wHigh - 52wLow)
    # Score 100 if at 52W high, 0 if at 52W low.
    current = info.get("currentPrice") or info.get("regularMarketPrice")
    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    if current and high52 and low52 and (high52 - low52) > 0:
        momentum_score = ((current - low52) / (high52 - low52)) * 100
        scores["momentum"] = round(momentum_score, 2)
        details["52W Position %"] = round(momentum_score, 2)
    else:
        scores["momentum"] = 0
        details["52W Position %"] = "N/A"

    # ── Analyst Upside Score ──────────────────────────────────────────────────
    # Upside = (target - current) / current * 100
    # Score 100 at 50%+ upside, 0 at 0% or below.
    target = info.get("targetMeanPrice")
    if target and current and current > 0:
        upside_pct = (target - current) / current * 100
        upside_score = max(0, min(100, upside_pct * 2))
        scores["upside"] = upside_score
        details["Analyst Upside %"] = round(upside_pct, 2)
    else:
        scores["upside"] = 0
        details["Analyst Upside %"] = "N/A"

    # ── Dividend Yield Score ──────────────────────────────────────────────────
    # Score 100 at 5%+ yield, 0 at 0%.
    div_yield = info.get("dividendYield")
    if div_yield and div_yield > 0:
        yield_pct = div_yield * 100
        yield_score = min(100, yield_pct * 20)
        scores["div_yield"] = yield_score
        details["Div Yield %"] = round(yield_pct, 2)
    else:
        scores["div_yield"] = 0
        details["Div Yield %"] = "N/A"

    # ── Weighted total ────────────────────────────────────────────────────────
    total_weight = sum(weights.values()) or 1
    weighted_score = sum(
        scores.get(factor, 0) * weight
        for factor, weight in weights.items()
    ) / total_weight

    return {"score": round(weighted_score, 2), **details}


# ── Weight configuration ───────────────────────────────────────────────────────

st.subheader("Scoring Weights")
st.caption("Adjust weights for each factor. Higher weight = more influence on the final score.")

# Load saved configs
saved_configs = get_screener_configs()

# Config profile selector
config_names = list(saved_configs.keys())
selected_config = None

if config_names:
    col_cfg1, col_cfg2 = st.columns([2, 1])
    with col_cfg1:
        selected_config = st.selectbox(
            "Load saved profile", ["— New profile —"] + config_names
        )
    with col_cfg2:
        if selected_config and selected_config != "— New profile —":
            if st.button("🗑 Delete profile", type="primary"):
                delete_screener_config(selected_config)
                st.rerun()

# Default weights or load from saved config
if selected_config and selected_config in saved_configs:
    default_weights = saved_configs[selected_config]
else:
    from database import get_setting
    default_weights = {
        "pe": float(str(get_setting("screener_w_pe", "1.0"))),
        "growth": float(str(get_setting("screener_w_growth", "1.0"))),
        "momentum": float(str(get_setting("screener_w_momentum", "1.0"))),
        "upside": float(str(get_setting("screener_w_upside", "1.0"))),
        "div_yield": float(str(get_setting("screener_w_div_yield", "1.0"))),
    }
w_col1, w_col2, w_col3, w_col4, w_col5 = st.columns(5)
w_pe = w_col1.slider("P/E", 0.0, 3.0, float(default_weights.get("pe", 1.0)), 0.5)
w_growth = w_col2.slider("EPS Growth", 0.0, 3.0, float(default_weights.get("growth", 1.0)), 0.5)
w_momentum = w_col3.slider("Momentum", 0.0, 3.0, float(default_weights.get("momentum", 1.0)), 0.5)
w_upside = w_col4.slider("Analyst Upside", 0.0, 3.0, float(default_weights.get("upside", 1.0)), 0.5)
w_div = w_col5.slider("Div Yield", 0.0, 3.0, float(default_weights.get("div_yield", 1.0)), 0.5)

weights = {
    "pe": w_pe,
    "growth": w_growth,
    "momentum": w_momentum,
    "upside": w_upside,
    "div_yield": w_div,
}

# Save config
with st.form("save_config_form", clear_on_submit=True):
    save_col1, save_col2 = st.columns([2, 1])
    config_name = save_col1.text_input("Save profile as", placeholder="e.g. Growth Focus")
    if save_col2.form_submit_button("Save Profile"):
        if config_name.strip():
            save_screener_config(config_name.strip(), weights)
            st.success(f"Profile '{config_name}' saved.")
            st.rerun()
        else:
            st.error("Enter a profile name.")

st.divider()

# ── Ticker input ───────────────────────────────────────────────────────────────

st.subheader("Tickers to Screen")
st.caption("Enter tickers separated by commas.")

ticker_input = st.text_input(
    "Tickers",
    placeholder="e.g. AAPL, MSFT, GOOGL, JNJ, KO",
    label_visibility="collapsed",
)

run_screen = st.button("Run Screener", type="primary")

st.divider()

# ── Run screener ───────────────────────────────────────────────────────────────

if run_screen:
    if not ticker_input.strip():
        st.error("Enter at least one ticker.")
    else:
        raw_tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

        results = []
        progress = st.progress(0, text="Fetching data...")

        for i, ticker in enumerate(raw_tickers):
            progress.progress((i + 1) / len(raw_tickers), text=f"Fetching {ticker}...")
            info = get_ticker_info(ticker)
            if not info:
                st.warning(f"Could not fetch data for {ticker} — skipping.")
                continue
            result = score_ticker(info, weights)
            result["Ticker"] = ticker
            result["Name"]   = info.get("longName", ticker)
            results.append(result)

        progress.empty()

        if not results:
            st.error("No valid results returned.")
        else:
            results_df = pd.DataFrame(results)
            col_order = ["Ticker", "Name", "score", "P/E", "EPS Growth %",
                         "52W Position %", "Analyst Upside %", "Div Yield %"]
            results_df = results_df[[c for c in col_order if c in results_df.columns]]
            results_df = results_df.rename(columns={"score": "Score"})
            results_df = results_df.sort_values("Score", ascending=False).reset_index(drop=True)
            results_df.index += 1

            # Store in session state so results survive reruns
            st.session_state["screener_results"] = results_df

# ── Display results (persists across reruns via session_state) ────────────────

if "screener_results" in st.session_state:
    results_df = st.session_state["screener_results"]

    st.subheader("Screener Results")

    display_df = results_df.copy()
    for col in ["P/E", "EPS Growth %", "52W Position %", "Analyst Upside %", "Div Yield %"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"{x:.2f}" if isinstance(x, float) else x
            )
    display_df["Score"] = display_df["Score"].apply(
        lambda x: f"{x:.2f}" if isinstance(x, float) else x
    )

    st.dataframe(display_df, use_container_width=True)

    st.divider()

    # ── Add to watchlist ───────────────────────────────────────────────────────

    st.subheader("Add to Watchlist")

    with st.form("add_to_watchlist_form"):
        watchlist_ticker = st.selectbox(
            "Select ticker to add",
            results_df["Ticker"].tolist(),
        )
        if st.form_submit_button("Add to Watchlist"):
            if watchlist_ticker:
                add_to_watchlist(ticker=watchlist_ticker)
                st.success(f"{watchlist_ticker} added to watchlist.")
            else:
                st.error("No ticker selected.")

