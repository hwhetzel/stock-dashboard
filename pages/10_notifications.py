import streamlit as st
import json
from datetime import datetime, timedelta
from database import (
    initialize_db,
    get_notifications,
    mark_all_notifications_read,
    delete_notification,
    delete_notifications,
    delete_all_notifications,
    get_unread_count,
    add_notification,
    get_transactions,
    get_watchlist,
    get_setting,
    set_setting,
)
from data import get_bulk_current_prices, get_earnings_dates

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Notifications", layout="wide")
initialize_db()

from utils.theme import apply_theme
apply_theme()

st.title("Notifications")

# ── Session summary generator ─────────────────────────────────────────────────

def get_held_tickers(transactions):
    by_ticker = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)
    held = []
    for ticker, txs in by_ticker.items():
        shares = 0.0
        cost_basis = 0.0
        for tx in txs:
            if tx["type"] == "buy":
                cost_basis += tx["shares"] * tx["price"]
                shares += tx["shares"]
            elif tx["type"] == "sell":
                avg = cost_basis / shares if shares else 0
                sell = min(tx["shares"], shares)
                cost_basis -= sell * avg
                shares -= sell
        if shares > 0.0001:
            held.append({"ticker": ticker, "shares": shares, "cost_basis": cost_basis})
    return held


def generate_session_summary() -> dict:
    """
    Build a summary dict of what changed since the last session.
    Checks: holdings movement, watchlist price changes,
    upcoming earnings (next 7 days), upcoming dividends.
    """
    from database import get_setting
    price_threshold = float(str(get_setting("notify_price_change_pct", "2.0")))
    watch_threshold = float(str(get_setting("notify_watchlist_change_pct", "1.0")))
    earnings_days = int(str(get_setting("notify_earnings_lead_days", "7")))
    notify_holdings_on = get_setting("notify_holdings", "1") == "1"
    notify_watchlist_on = get_setting("notify_watchlist", "1") == "1"
    notify_earnings_on = get_setting("notify_earnings", "1") == "1"

    transactions = get_transactions()
    holdings = get_held_tickers(transactions)
    watchlist = get_watchlist()

    tickers_held = [h["ticker"] for h in holdings]
    tickers_watch = [w["ticker"] for w in watchlist]
    all_tickers = list(dict.fromkeys(tickers_held + tickers_watch))

    prices = get_bulk_current_prices(all_tickers)

    # ── Holdings movement (>2% change today) ─────────────────────────────────
    import yfinance as yf
    holdings_movement = []
    for h in holdings:
        ticker = h["ticker"]
        try:
            info = yf.Ticker(ticker).fast_info
            current = info.get("last_price")
            prev = info.get("previous_close")
            if current and prev and prev > 0:
                change_pct = (current - prev) / prev * 100
                if notify_holdings_on and abs(change_pct) >= price_threshold:
                    holdings_movement.append({
                        "ticker": ticker,
                        "change_pct": round(change_pct, 2),
                        "price": round(current, 2),
                    })
        except Exception:
            pass

    # ── Watchlist price changes (>1% change today) ────────────────────────────
    watchlist_changes = []
    for w in watchlist:
        ticker = w["ticker"]
        try:
            info = yf.Ticker(ticker).fast_info
            current = info.get("last_price")
            prev = info.get("previous_close")
            if current and prev and prev > 0:
                change_pct = (current - prev) / prev * 100
                if notify_watchlist_on and abs(change_pct) >= watch_threshold:
                    watchlist_changes.append({
                        "ticker": ticker,
                        "change_pct": round(change_pct, 2),
                        "price": round(current, 2),
                        "target": w.get("target_price"),
                    })
        except Exception:
            pass

    # ── Upcoming earnings (next 7 days) ───────────────────────────────────────
    upcoming_earnings = []
    now = datetime.now()
    week_end = now + timedelta(days=earnings_days)
    for ticker in all_tickers:
        try:
            df = get_earnings_dates(ticker, limit=4)
            if df.empty:
                continue
            df.index = df.index if hasattr(df.index, "tz") else df.index
            for dt in df.index:
                dt_naive = dt.tz_localize(None) if dt.tzinfo else dt
                if notify_earnings_on and now <= dt_naive <= week_end:
                    upcoming_earnings.append({
                        "ticker": ticker,
                        "date": dt_naive.strftime("%Y-%m-%d"),
                    })
        except Exception:
            pass

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "holdings_movement": holdings_movement,
        "watchlist_changes": watchlist_changes,
        "upcoming_earnings": upcoming_earnings,
    }


# ── Auto-generate summary on first visit this session ────────────────────────

if "notification_generated" not in st.session_state:
    st.session_state["notification_generated"] = True
    with st.spinner("Generating session summary..."):
        summary = generate_session_summary()
        # Only save if there's something worth noting
        has_content = (
            summary["holdings_movement"]
            or summary["watchlist_changes"]
            or summary["upcoming_earnings"]
        )
        if has_content:
            add_notification(summary)

# ── Mark all read when page is opened ────────────────────────────────────────

mark_all_notifications_read()

# ── Load notifications ────────────────────────────────────────────────────────

notifications = get_notifications()
unread = get_unread_count()

if unread > 0:
    st.info(f"📬 {unread} unread notification{'s' if unread != 1 else ''}")

# ── Bulk actions ──────────────────────────────────────────────────────────────

if notifications:
    st.markdown("**Bulk Actions**")
    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 4])

    select_all = bulk_col1.button("Select All")
    clear_all  = bulk_col2.button("🗑 Clear All", type="primary")

    if clear_all:
        st.session_state["confirm_clear_all"] = True

    if st.session_state.get("confirm_clear_all"):
        st.warning("Are you sure you want to delete all notifications?")
        conf_col1, conf_col2 = st.columns([1, 5])
        if conf_col1.button("Yes, delete all"):
            delete_all_notifications()
            st.session_state.pop("confirm_clear_all", None)
            st.rerun()
        if conf_col2.button("Cancel"):
            st.session_state.pop("confirm_clear_all", None)
            st.rerun()

    if select_all:
        st.session_state["selected_ids"] = [n["id"] for n in notifications]

    # Delete selected
    selected_ids = st.session_state.get("selected_ids", [])
    if selected_ids:
        if st.button(f"🗑 Delete Selected ({len(selected_ids)})"):
            st.session_state["confirm_delete_selected"] = True

        if st.session_state.get("confirm_delete_selected"):
            st.warning(f"Delete {len(selected_ids)} selected notification(s)?")
            dc1, dc2 = st.columns([1, 5])
            if dc1.button("Yes, delete"):
                delete_notifications(selected_ids)
                st.session_state.pop("selected_ids", None)
                st.session_state.pop("confirm_delete_selected", None)
                st.rerun()
            if dc2.button("Cancel "):
                st.session_state.pop("confirm_delete_selected", None)
                st.rerun()

    st.divider()

# ── Notification list ─────────────────────────────────────────────────────────

if not notifications:
    st.info("No notifications yet. They will appear here when you open the app and there are changes to report.")
else:
    if "selected_ids" not in st.session_state:
        st.session_state["selected_ids"] = []

    for notif in notifications:
        n_id = notif["id"]
        summary = notif["summary"]
        created = notif["created_at"]
        is_selected = n_id in st.session_state["selected_ids"]

        with st.expander(f"📋 Session — {created}", expanded=False):
            # Checkbox for selection
            checked = st.checkbox("Select", value=is_selected, key=f"chk_{n_id}")
            if checked and n_id not in st.session_state["selected_ids"]:
                st.session_state["selected_ids"].append(n_id)
            elif not checked and n_id in st.session_state["selected_ids"]:
                st.session_state["selected_ids"].remove(n_id)

            # ── Holdings movement ─────────────────────────────────────────────
            movements = summary.get("holdings_movement", [])
            if movements:
                st.markdown("**📈 Holdings Movement (≥2% today)**")
                for m in movements:
                    sign = "+" if m["change_pct"] >= 0 else ""
                    color = "green" if m["change_pct"] >= 0 else "red"
                    st.markdown(
                        f"<span style='color:{color}'>{m['ticker']} "
                        f"${m['price']} ({sign}{m['change_pct']}%)</span>",
                        unsafe_allow_html=True,
                    )

            # ── Watchlist changes ─────────────────────────────────────────────
            changes = summary.get("watchlist_changes", [])
            if changes:
                st.markdown("**👀 Watchlist Changes (≥1% today)**")
                for c in changes:
                    sign = "+" if c["change_pct"] >= 0 else ""
                    color = "green" if c["change_pct"] >= 0 else "red"
                    target_str = f" | Target: ${c['target']:.2f}" if c.get("target") else ""
                    st.markdown(
                        f"<span style='color:{color}'>{c['ticker']} "
                        f"${c['price']} ({sign}{c['change_pct']}%){target_str}</span>",
                        unsafe_allow_html=True,
                    )

            # ── Upcoming earnings ─────────────────────────────────────────────
            earnings = summary.get("upcoming_earnings", [])
            if earnings:
                st.markdown("**📅 Upcoming Earnings (next 7 days)**")
                for e in earnings:
                    st.markdown(f"- {e['ticker']} — {e['date']}")

            # ── Delete individual ─────────────────────────────────────────────
            if st.button("🗑 Delete", key=f"del_{n_id}"):
                st.session_state["confirm_delete_id"] = n_id

            if st.session_state.get("confirm_delete_id") == n_id:
                st.warning("Delete this notification?")
                d1, d2 = st.columns([1, 5])
                if d1.button("Yes", key=f"yes_{n_id}"):
                    delete_notification(n_id)
                    st.session_state.pop("confirm_delete_id", None)
                    st.rerun()
                if d2.button("No", key=f"no_{n_id}"):
                    st.session_state.pop("confirm_delete_id", None)
                    st.rerun()