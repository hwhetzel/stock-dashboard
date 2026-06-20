import streamlit as st
from database import initialize_db, get_transactions
from data import get_bulk_current_prices, get_news, get_ticker_info

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Stock Dashboard",
    page_icon="📈",
    layout="wide",
)

initialize_db()

from utils.theme import apply_theme
apply_theme()

# ── Header ────────────────────────────────────────────────────────────────────

st.title("📈 Stock Dashboard")
st.caption("Your personal portfolio overview.")

st.divider()

# ── Portfolio summary metrics ─────────────────────────────────────────────────

transactions = get_transactions()

def compute_summary(transactions):
    """
    Re-derive holdings from transactions and fetch live prices.
    Returns total portfolio value, cost basis, and unrealized G/L.
    """
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
                cost_basis  -= sell * avg
                shares_held -= sell
        if shares_held > 0.0001:
            holdings.append({
                "ticker": ticker,
                "shares": shares_held,
                "cost_basis": cost_basis,
            })

    if not holdings:
        return None

    tickers = [h["ticker"] for h in holdings]
    prices = get_bulk_current_prices(tickers)

    total_value = sum(h["shares"] * prices.get(h["ticker"], 0) for h in holdings)
    total_cost = sum(h["cost_basis"] for h in holdings)
    total_unreal = total_value - total_cost
    total_unreal_p = (total_unreal / total_cost * 100) if total_cost else 0

    return {
        "holdings": holdings,
        "prices": prices,
        "total_value": total_value,
        "total_cost": total_cost,
        "total_unreal": total_unreal,
        "total_unreal_p": total_unreal_p,
        "num_holdings": len(holdings),
    }

summary = compute_summary(transactions)

if summary is None:
    st.info("No holdings yet — head to the **Portfolio** page to add transactions.")
else:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Value", f"${summary['total_value']:,.2f}")
    c2.metric("Total Cost Basis", f"${summary['total_cost']:,.2f}")
    c3.metric(
        "Unrealized G/L",
        f"${summary['total_unreal']:,.2f}",
        delta=f"{summary['total_unreal_p']:.2f}%",
    )
    c4.metric("Holdings", summary["num_holdings"])

    st.divider()

    # ── Per-holding snapshot ──────────────────────────────────────────────────

    st.subheader("Holdings Snapshot")

    cols = st.columns(min(len(summary["holdings"]), 4))
    for i, h in enumerate(summary["holdings"]):
        ticker = h["ticker"]
        price = summary["prices"].get(ticker)
        mkt_val = h["shares"] * price if price else None
        unreal = mkt_val - h["cost_basis"] if mkt_val else None
        unreal_p = (unreal / h["cost_basis"] * 100) if unreal and h["cost_basis"] else None

        col = cols[i % 4]
        with col:
            st.markdown(f"**{ticker}**")
            if price is not None:
                st.markdown(f"${price:,.2f}")
            if unreal is not None and unreal_p is not None:
                color = "green" if unreal >= 0 else "red"
                sign  = "+" if unreal >= 0 else ""
                st.markdown(
                    f"<span style='color:{color}'>{sign}${unreal:,.2f} "
                    f"({sign}{unreal_p:.2f}%)</span>",
                    unsafe_allow_html=True,
                )
            st.caption(f"{h['shares']:.4f} shares")

    st.divider()

    # ── News feed for holdings ────────────────────────────────────────────────

    st.subheader("Latest News")

    # Let the user pick which holding to show news for
    tickers_held = [h["ticker"] for h in summary["holdings"]]
    news_ticker = st.selectbox("News for", tickers_held, label_visibility="collapsed")

    articles = get_news(news_ticker or "", limit=8)
    if not articles:
        st.caption("No recent news found.")
    else:
        for article in articles:
            title = article.get("title", "No title")
            publisher = article.get("publisher", "")
            link = article.get("link", "#")
            st.markdown(f"- [{title}]({link}) — *{publisher}*")

    st.divider()

    # ── Quick links ───────────────────────────────────────────────────────────

    st.subheader("Quick Links")

    ql1, ql2, ql3, ql4 = st.columns(4)
    ql1.page_link("pages/1_portfolio.py", label="Portfolio",  icon="💼")
    ql2.page_link("pages/2_allocation.py", label="Allocation", icon="🥧")
    ql3.page_link("pages/4_dividends.py", label="Dividends",  icon="💰")
    ql4.page_link("pages/5_analytics.py", label="Analytics",  icon="📊")

    ql5, ql6, ql7, ql8 = st.columns(4)
    ql5.page_link("pages/3_watchlist.py", label="Watchlist",  icon="👀")
    ql6.page_link("pages/6_charts.py", label="Charts",     icon="📉")
    ql7.page_link("pages/7_earnings.py", label="Earnings",   icon="📅")
    ql8.page_link("pages/8_screener.py", label="Screener",   icon="🔍")