import streamlit as st
import webbrowser
from datetime import datetime
from database import initialize_db, get_transactions, get_watchlist
from data import get_news, get_bulk_current_prices
from database import initialize_db, get_setting, set_setting

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="News", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

from utils.price_monitor import run_idle_monitor
run_idle_monitor()

st.title("News")

col_slider, col_btn, _ = st.columns([1, 1, 2])
articles_per_ticker = col_slider.number_input(
    "Articles per ticker",
    min_value=1, max_value=20,
    value=int(str(get_setting("news_articles_per_ticker", "8"))),
    step=1,
)
col_btn.write("")
col_btn.write("")
if col_btn.button("Save as default"):
    set_setting("news_articles_per_ticker", str(articles_per_ticker))
    st.success("Saved as default.")

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

# Combine, deduplicate, held tickers first
all_tickers = list(dict.fromkeys(held_tickers + watch_tickers))

if not all_tickers:
    st.info("No holdings or watchlist tickers yet.")
    st.stop()

# ── Fetch current prices for badge coloring ───────────────────────────────────
# Badge color: green = up today, red = down today, blue = neutral/unknown

prices = get_bulk_current_prices(all_tickers)

def get_badge_color(ticker: str) -> str:
    """
    Determine badge color based on today's price movement.
    Uses previous close from yfinance fast_info to determine direction.
    Falls back to blue if data unavailable.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).fast_info
        current = info.get("last_price")
        prev = info.get("previous_close")
        if current and prev:
            if current > prev:
                return "#1a7a1a"   # green
            elif current < prev:
                return "#a00000"   # red
    except Exception:
        pass
    return "#1a5276"               # blue neutral


# ── Ticker filter ─────────────────────────────────────────────────────────────

st.markdown("**Filter by ticker**")
col1, col2 = st.columns([2, 4])

with col1:
    filter_options = ["All Tickers"] + all_tickers
    selected_filter = st.selectbox("Ticker", filter_options, label_visibility="collapsed")

tickers_to_show = all_tickers if selected_filter == "All Tickers" else [selected_filter]

st.divider()

# ── News feed ─────────────────────────────────────────────────────────────────

# cap per ticker to avoid overwhelming the feed
#ARTICLES_PER_TICKER = int(str(get_setting("news_articles_per_ticker", "8")))
   

all_articles = []

for ticker in tickers_to_show:
    articles = get_news(ticker, limit=articles_per_ticker)
    badge_color = get_badge_color(ticker)
    for article in articles:
        all_articles.append({
            "ticker": ticker,
            "title": article.get("title", "No title"),
            "publisher": article.get("publisher", ""),
            "link": article.get("link", "#"),
            "badge_color": badge_color,
            "published": article.get("published", "")
        })

if not all_articles:
    st.info("No news found for current tickers.")
    st.stop()

# ── Render articles ───────────────────────────────────────────────────────────

for article in all_articles:
    ticker = article["ticker"]
    title = article["title"]
    publisher = article["publisher"]
    link = article["link"]
    badge_color = article["badge_color"]
    published = article["published"]

    # Ticker badge + headline on same line
    badge_html = (
        f"<span style='"
        f"background-color:{badge_color};"
        f"color:white;"
        f"padding:2px 8px;"
        f"border-radius:4px;"
        f"font-size:0.75rem;"
        f"font-weight:bold;"
        f"margin-right:8px;"
        f"'>{ticker}</span>"
    )

    published = article.get("published", "")
    pub_str = f" -- {published}" if published else ""

    st.markdown(
        f"{badge_html}"
        f"<a href='{link}' target='_blank' style='text-decoration:none;font-size:0.95rem;'>"
        f"{title}</a>"
        f"<span style='color:gray;font-size:0.8rem;margin-left:8px;'>— {publisher}{pub_str}</span>",
        unsafe_allow_html=True,
    )

st.divider()
st.caption(f"Showing up to {articles_per_ticker} articles per ticker. Links open in your default browser.")