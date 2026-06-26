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
    get_known_accounts
)
from data import get_earnings_dates

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Notifications", layout="wide")
initialize_db()


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
        accounts = set()
        for tx in txs:
            if tx.get("account"):
                accounts.add(tx["account"])
            if tx["type"] == "buy":
                cost_basis += tx["shares"] * tx["price"]
                shares += tx["shares"]
            elif tx["type"] == "sell":
                avg = cost_basis / shares if shares else 0
                sell = min(tx["shares"], shares)
                cost_basis -= sell * avg
                shares -= sell
        if shares > 0.0001:
            held.append({
                "ticker": ticker,
                "shares": shares,
                "cost_basis": cost_basis,
                "accounts": ", ".join(sorted(accounts)) if accounts else "",
            })
    return held


def generate_session_summary() -> dict:
    """
    Build a summary dict of what changed since the last session.
    Checks: holdings movement, watchlist price changes,
    upcoming earnings (next 7 days), upcoming dividends.
    """

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


    # ── Holdings movement (>2% change today) ─────────────────────────────────
    import yfinance as yf
    holdings_movement = []
    if notify_holdings_on:
        for h in holdings:
            ticker = h["ticker"]
            try:
                fi = yf.Ticker(ticker).fast_info
                current = fi.last_price
                prev = fi.previous_close
                if current and prev and prev > 0:
                    change_pct = (current - prev) / prev * 100
                    if abs(change_pct) >= price_threshold:
                        holdings_movement.append({
                            "ticker": ticker,
                            "change_pct": round(change_pct, 2),
                            "price": round(current, 2),
                            "accounts": h.get("accounts", ""),
                        })
            except Exception:
                pass

    # ── Watchlist price changes (>1% change today) ────────────────────────────
    watchlist_changes = []
    if notify_watchlist_on:
        for w in watchlist:
            ticker = w["ticker"]
            try:
                fi = yf.Ticker(ticker).fast_info
                current = fi.last_price
                prev = fi.previous_close
                if current and prev and prev > 0:
                    change_pct = (current - prev) / prev * 100
                    if abs(change_pct) >= watch_threshold:
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

# ── Bulk actions ─────────────────────────────────────────────────────────────

if notifications:
    if "selected_ids" not in st.session_state:
        st.session_state["selected_ids"] = []

    bulk_col1, bulk_col2, bulk_col3, bulk_col4 = st.columns([1, 1, 1, 3])

    if bulk_col1.button("Select All"):
        st.session_state["selected_ids"] = [n["id"] for n in notifications]
        for n in notifications:
            st.session_state[f"chk_{n['id']}"] = True
        st.rerun()

    if bulk_col2.button("Deselect All"):
        st.session_state["selected_ids"] = []
        for n in notifications:
            st.session_state[f"chk_{n['id']}"] = False
        st.rerun()

    if bulk_col3.button("🗑 Clear All", type="primary"):
        st.session_state["confirm_clear_all"] = True

    if st.session_state.get("confirm_clear_all"):
        st.warning("Are you sure you want to delete all notifications?")
        conf_col1, conf_col2 = st.columns([1, 5])
        if conf_col1.button("Yes, delete all", key="confirm_clear_all_yes"):
            delete_all_notifications()
            st.session_state["selected_ids"] = []
            st.session_state.pop("confirm_clear_all", None)
            st.rerun()
        if conf_col2.button("Cancel", key="confirm_clear_all_cancel"):
            st.session_state.pop("confirm_clear_all", None)
            st.rerun()

    selected_ids = st.session_state.get("selected_ids", [])
    if selected_ids:
        if st.button(f"🗑 Delete Selected ({len(selected_ids)})", key="delete_selected_btn"):
            st.session_state["confirm_delete_selected"] = True

        if st.session_state.get("confirm_delete_selected"):
            st.warning(f"Delete {len(selected_ids)} selected notification(s)?")
            dc1, dc2 = st.columns([1, 5])
            if dc1.button("Yes, delete", key="confirm_delete_selected_yes"):
                delete_notifications(list(selected_ids))
                st.session_state["selected_ids"] = []
                st.session_state.pop("confirm_delete_selected", None)
                st.rerun()
            if dc2.button("Cancel", key="confirm_delete_selected_cancel"):
                st.session_state.pop("confirm_delete_selected", None)
                st.rerun()

    st.divider()

# ── Notification list ─────────────────────────────────────────────────────────

if not notifications:
    st.info("No notifications yet. They will appear here when you open the app and there are changes to report.")
else:
    for notif in notifications:
        n_id = notif["id"]
        summary = notif["summary"]
        created = notif["created_at"]

        # Title differs based on notification type
        notif_type = summary.get("type", "session")
        if notif_type == "csv_import":
            expander_title = f"📥 CSV Import — {created}"
        elif notif_type == "price_alert":
            expander_title = f"🔔 Alert — {created}"
        else:
            expander_title = f"📋 Session — {created}"

        with st.expander(expander_title, expanded=False):
            def on_check(nid=n_id):
                key = f"chk_{nid}"
                if st.session_state[key]:
                    if nid not in st.session_state["selected_ids"]:
                        st.session_state["selected_ids"].append(nid)
                else:
                    if nid in st.session_state["selected_ids"]:
                        st.session_state["selected_ids"].remove(nid)

            st.checkbox(
                "Select for deletion",
                value=n_id in st.session_state.get("selected_ids", []),
                key=f"chk_{n_id}",
                on_change=on_check,
            )

            # ── CSV Import summary ────────────────────────────────────────────
            if notif_type == "csv_import":
                accounts = summary.get("accounts", [])
                total = summary.get("total_positions", 0)
                st.markdown(f"**Imported {total} positions**" + (f" from: {', '.join(accounts)}" if accounts else ""))

                added = summary.get("added", [])
                if added:
                    st.markdown("**🟢 New positions added**")
                    for t in added:
                        st.markdown(f"- {t}")

                removed = summary.get("removed", [])
                if removed:
                    st.markdown("**🔴 Positions closed**")
                    for t in removed:
                        st.markdown(f"- {t}")

                changed = summary.get("changed", [])
                if changed:
                    st.markdown("**🔄 Share count changes**")
                    for c in changed:
                        diff = c["share_diff"]
                        direction = "▲" if diff > 0 else "▼"
                        color = "green" if diff > 0 else "red"
                        st.markdown(
                            f"<span style='color:{color}'>**{c['symbol']}** "
                            f"{c['old_shares']} → {c['new_shares']} shares "
                            f"({direction}{abs(diff):.4f})</span>",
                            unsafe_allow_html=True,
                        )

                moved = summary.get("moved_from_watchlist", [])
                if moved:
                    st.markdown("**📋 Removed from watchlist (now in portfolio)**")
                    for t in moved:
                        st.markdown(f"- {t}")

                if not any([added, removed, changed, moved]):
                    st.info("No changes detected since last import.")

        # ── Price alert summary ───────────────────────────────────────────
            elif notif_type == "price_alert":
                alerts = summary.get("alerts", [])
                if not alerts:
                    st.info("No alert details available.")
                else:
                    # Group by threshold type
                    holdings_alerts = [a for a in alerts if a["threshold_type"] == "Holdings Movement"]
                    watchlist_alerts = [a for a in alerts if a["threshold_type"] == "Watchlist Change"]
                    earnings_alerts = [a for a in alerts if a["threshold_type"] == "Upcoming Earnings"]
                    dividend_alerts = [a for a in alerts if a["threshold_type"] == "Upcoming Ex-Dividend"]

                    if holdings_alerts:
                        st.markdown("**📈 Holdings Movement**")
                        for a in holdings_alerts:
                            sign = "+" if a["change_pct"] >= 0 else ""
                            color = "green" if a["change_pct"] >= 0 else "red"
                            st.markdown(
                                f"<span style='color:{color}'>{a['ticker']} "
                                f"${a['price']} ({sign}{a['change_pct']}%)</span>",
                                unsafe_allow_html=True,
                            )

                    if watchlist_alerts:
                        st.markdown("**👀 Watchlist Change**")
                        for a in watchlist_alerts:
                            sign = "+" if a["change_pct"] >= 0 else ""
                            color = "green" if a["change_pct"] >= 0 else "red"
                            st.markdown(
                                f"<span style='color:{color}'>{a['ticker']} "
                                f"${a['price']} ({sign}{a['change_pct']}%)</span>",
                                unsafe_allow_html=True,
                            )

                    if earnings_alerts:
                        st.markdown("**📅 Upcoming Earnings**")
                        for a in earnings_alerts:
                            st.markdown(f"- {a['ticker']} — {a['date']} ({a['days_away']} day(s) away)")

                    if dividend_alerts:
                        st.markdown("**💰 Upcoming Ex-Dividend**")
                        for a in dividend_alerts:
                            st.markdown(f"- {a['ticker']} — {a['date']} ({a['days_away']} day(s) away)")

            # ── Session summary ───────────────────────────────────────────────
            else:
                movements = summary.get("holdings_movement", [])
                show_account_col = (
                    get_setting("has_multiple_accounts", "false") == "true"
                    or len(get_known_accounts()) > 1
                )
                if movements:
                    st.markdown("**📈 Holdings Movement (≥2% today)**")
                    for m in movements:
                        sign = "+" if m["change_pct"] >= 0 else ""
                        color = "green" if m["change_pct"] >= 0 else "red"
                        acct_str = f" | {m['accounts']}" if show_account_col and m.get("accounts") else ""
                        st.markdown(
                            f"<span style='color:{color}'>{m['ticker']}"
                            f"{acct_str} "
                            f"${m['price']} ({sign}{m['change_pct']}%)</span>",
                            unsafe_allow_html=True,
                        )

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
                    if n_id in st.session_state.get("selected_ids", []):
                        st.session_state["selected_ids"].remove(n_id)
                    st.rerun()
                if d2.button("No", key=f"no_{n_id}"):
                    st.session_state.pop("confirm_delete_id", None)
                    st.rerun()