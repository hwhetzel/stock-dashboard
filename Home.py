import streamlit as st
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from database import initialize_db, get_transactions, get_setting, get_known_accounts, upsert_portfolio_snapshot, get_unread_count, get_all_holding_notes
from data import get_bulk_current_prices, get_news, get_earnings_dates, get_company_names
from utils.theme import apply_theme, show_notification_badge

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Stock Dashboard", page_icon="📈", layout="wide")

initialize_db()
apply_theme()
_badge_count = get_unread_count()
show_notification_badge(count=_badge_count)

# ── Weekly CSV reminder banner ────────────────────────────────────────────────

last_import = get_setting("last_csv_import", None)
if last_import and get_setting("csv_weekly_reminder", "0") == "1":
    try:
        last_dt = datetime.strptime(last_import, "%Y-%m-%d")
        if datetime.now() - last_dt >= timedelta(days=7):
            st.warning(f"⏰ It's been 7+ days since your last CSV import ({last_import}). Consider importing a fresh export on the Portfolio page.")
    except ValueError:
        pass

# ── Holdings builder ──────────────────────────────────────────────────────────

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

# ── Load data ─────────────────────────────────────────────────────────────────

transactions = get_transactions()
holdings = compute_holdings(transactions)

st.title("📈 Stock Dashboard")
st.caption(f"Last updated: {datetime.now().strftime('%b %d, %Y %I:%M %p')}")
st.divider()

if not holdings:
    st.info("No holdings yet — head to the **Portfolio** page to add transactions.")
    st.stop()

tickers = [h["ticker"] for h in holdings]

_loading_banner = st.empty()
_loading_banner.markdown(
    """
    <div style="
        background-color: #c0392b;
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 1rem;
        font-weight: bold;
        text-align: center;
        letter-spacing: 0.3px;
    ">
        ⚠️ Loading portfolio — please wait before navigating away...
    </div>
    """,
    unsafe_allow_html=True,
)
with st.spinner(""):
    prices = get_bulk_current_prices(tickers)
    company_names = get_company_names(tickers)
    holding_notes = get_all_holding_notes()

    # Pre-fetch news and earnings inside the spinner so they're ready when page renders
    news_items_raw = {}
    for ticker in tickers:
        news_items_raw[ticker] = get_news(ticker, limit=2)

    earnings_soon = []
    now = datetime.now()
    week_end = now + timedelta(days=7)
    for ticker in tickers:
        try:
            df = get_earnings_dates(ticker, limit=4)
            if df.empty:
                continue
            for dt in df.index:
                dt_naive = dt.tz_localize(None) if hasattr(dt, "tzinfo") and dt.tzinfo else dt
                if now <= dt_naive <= week_end:
                    earnings_soon.append((ticker, dt_naive.strftime("%Y-%m-%d")))
        except Exception:
            pass

_loading_banner.empty()

# ── Day change data ───────────────────────────────────────────────────────────

def get_day_change(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).fast_info
        current = info.last_price
        prev = info.previous_close
        if current and prev and prev > 0:
            change = current - prev
            change_pct = (change / prev) * 100
            return {
                "current": round(current, 2),
                "prev": round(prev, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
    except Exception:
        pass
    return {"current": None, "prev": None, "change": None, "change_pct": None}

day_data = {h["ticker"]: get_day_change(h["ticker"]) for h in holdings}

# ── Portfolio totals ──────────────────────────────────────────────────────────

total_value = 0.0
total_cost = 0.0
total_day_change = 0.0

for h in holdings:
    ticker = h["ticker"]
    price = prices.get(ticker) or 0
    mkt_val = h["shares"] * price
    total_value += mkt_val
    total_cost += h["cost_basis"]
    d = day_data.get(ticker, {})
    if d.get("change") is not None:
        total_day_change += d["change"] * h["shares"]

total_unrealized = total_value - total_cost
total_unrealized_pct = (total_unrealized / total_cost * 100) if total_cost else 0
total_day_change_pct = (total_day_change / (total_value - total_day_change) * 100) if (total_value - total_day_change) else 0

# ── Save daily portfolio snapshot ─────────────────────────────────────────────
# Runs silently on every app open. If a snapshot already exists for today,
# it gets replaced with the latest value. Accumulates over time so analytics
# can use real observed values instead of reconstructed history.
if total_value > 0:
    upsert_portfolio_snapshot(
        date=datetime.now().strftime("%Y-%m-%d"),
        value=round(total_value, 2),
        cost_basis=round(total_cost, 2),
    )


# ── Portfolio summary cards ───────────────────────────────────────────────────

st.subheader("Portfolio Summary")
row1_c1, row1_c2, row1_c3 = st.columns(3)
row1_c1.metric("Portfolio Value", f"${total_value:,.2f}")
row1_c2.metric("Total Cost Basis", f"${total_cost:,.2f}")
row1_c3.metric("Holdings", len(holdings))

row2_c1, row2_c2, row2_c3 = st.columns(3)
row2_c1.metric(
    "Unrealized G/L",
    f"${total_unrealized:,.2f}",
    delta=f"{total_unrealized_pct:+.2f}%",
)
row2_c2.metric(
    "Total G/L",
    f"${total_unrealized:,.2f}",
    delta=f"{total_unrealized_pct:+.2f}%",
)
row2_c3.metric(
    "Day Change",
    f"${total_day_change:,.2f}",
    delta=f"{total_day_change_pct:+.2f}%",
)

st.divider()

# ── Holdings snapshot + news ──────────────────────────────────────────────────

snap_col, news_col = st.columns([3, 2])

# Determine if Account column should show
show_account_col = (
    get_setting("has_multiple_accounts", "false") == "true"
    or len(get_known_accounts()) > 1
)

with snap_col:
    st.subheader("Holdings Snapshot")
    snap_rows = []
    for h in holdings:
        ticker = h["ticker"]
        price = prices.get(ticker)
        mkt_val = h["shares"] * price if price else None
        unreal = (mkt_val - h["cost_basis"]) if mkt_val else None
        unreal_pct = (unreal / h["cost_basis"] * 100) if unreal and h["cost_basis"] else None
        d = day_data.get(ticker, {})
        row = {"Ticker": ticker}
        row["Company"] = company_names.get(ticker, ticker)
        if show_account_col:
            row["Account"] = h.get("accounts", "")
        row["Price"] = ...
        row["Price"] = f"${price:,.2f}" if price else "N/A"
        row["Value"] = f"${mkt_val:,.2f}" if mkt_val else "N/A"
        row["Day %"] = f"{d['change_pct']:+.2f}%" if d.get("change_pct") is not None else "N/A"
        row["Total G/L %"] = f"{unreal_pct:+.2f}%" if unreal_pct is not None else "N/A"
        if holding_notes.get(ticker):
            row["Note"] = "📝"
        else:
            row["Note"] = ""
        snap_rows.append(row)
    st.dataframe(snap_rows, use_container_width=True, hide_index=True)

with news_col:
    with st.container(border=True):
        st.subheader("Latest News")
        news_items = []
        for ticker in tickers:
            articles = news_items_raw.get(ticker, [])
            for a in articles:
                news_items.append({
                    "ticker": ticker,
                    "title": a.get("title", "No title"),
                    "publisher": a.get("publisher", ""),
                    "link": a.get("link", "#"),
                    "published": a.get("published", ""),
                })

        shown = news_items[:4]
        if not shown:
            st.caption("No news available.")
        else:
            html_lines = []
            for item in shown:
                ticker = item["ticker"]
                d = day_data.get(ticker, {})
                change = d.get("change_pct")
                if change is not None and change > 0:
                    badge_color = "#1a7a1a"
                elif change is not None and change < 0:
                    badge_color = "#a00000"
                else:
                    badge_color = "#1a5276"

                badge = (
                    f"<span style='background-color:{badge_color};color:white;"
                    f"padding:2px 6px;border-radius:4px;font-size:0.7rem;"
                    f"font-weight:bold;margin-right:6px;'>{ticker}</span>"
                )
                pub = (
                    f"<br><span style='color:gray;font-size:0.75rem;'>"
                    f"{item['publisher']} · {item['published']}</span>"
                ) if item["published"] else ""

                html_lines.append(
                    f"<div style='padding:6px 0;border-bottom:1px solid #2d3139;'>"
                    f"{badge}"
                    f"<a href='{item['link']}' target='_blank' "
                    f"style='text-decoration:none;font-size:0.88rem;'>"
                    f"{item['title']}</a>{pub}</div>"
                )
            st.markdown("".join(html_lines), unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            st.page_link("pages/9_News.py", label="View all news →")

st.divider()

# ── Today's market movements ──────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("Today's Market Movements")
    st.caption("Holdings that moved significantly today vs previous close.")

    significant_threshold = float(str(get_setting("notify_price_change_pct", "2.0")))
    moved = []
    for h in holdings:
        d = day_data.get(h["ticker"], {})
        if d.get("change_pct") is not None and abs(d["change_pct"]) >= significant_threshold:
            moved.append((h["ticker"], d["change_pct"], d["current"]))

    if moved:
        st.markdown("**📊 Holdings with significant moves today:**")
        for ticker, pct, price in moved:
            sign = "+" if pct >= 0 else ""
            color = "green" if pct >= 0 else "red"
            st.markdown(
                f"<span style='color:{color}'>**{ticker}** "
                f"${price} ({sign}{pct:.2f}%)</span>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No significant holdings movement today.")

    # earnings_soon already fetched during initial load spinner above

    if earnings_soon:
        st.markdown("**📅 Upcoming earnings (next 7 days):**")
        for ticker, dt in earnings_soon:
            st.markdown(f"- **{ticker}** — {dt}")

st.divider()

# ── Quick links ───────────────────────────────────────────────────────────────

with st.container(border=True):
    st.subheader("Quick Links")
    ql1, ql2, ql3, ql4, ql5, ql6 = st.columns(6)
    ql1.page_link("pages/1_Portfolio.py",       label="Portfolio",      icon="💼")
    ql2.page_link("pages/2_Allocation.py",      label="Allocation",     icon="🥧")
    ql3.page_link("pages/3_Watchlist.py",       label="Watchlist",      icon="👀")
    ql4.page_link("pages/4_Dividends.py",       label="Dividends",      icon="💰")
    ql5.page_link("pages/5_Analytics.py",       label="Analytics",      icon="📊")
    ql6.page_link("pages/6_Charts.py",          label="Charts",         icon="📉")

    ql7, ql8, ql9, ql10, ql11, _ = st.columns(6)
    ql7.page_link("pages/7_Earnings.py",        label="Earnings",       icon="📅")
    ql8.page_link("pages/8_Screener.py",        label="Screener",       icon="🔍")
    ql9.page_link("pages/9_News.py",            label="News",           icon="📰")
    ql10.page_link("pages/10_Notifications.py", label="Notifications",  icon="🔔")
    ql11.page_link("pages/11_Settings.py",      label="Settings",       icon="⚙️")

    # ── Refresh badge if new notification was created after page loaded ────────────
import time
time.sleep(2)
_new_count = get_unread_count()
if _new_count != _badge_count:
    st.rerun()