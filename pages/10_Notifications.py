import streamlit as st
import json
from datetime import datetime
from database import (
    initialize_db,
    get_notifications,
    mark_all_notifications_read,
    delete_notification,
    delete_notifications,
    delete_all_notifications,
    get_unread_count,
    get_setting,
    get_known_accounts
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Notifications", layout="wide")
initialize_db()


st.title("Notifications")


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

PAGE_SIZE = 10

if not notifications:
    st.info("No notifications yet. They will appear here when you open the app and there are changes to report.")
else:
    # ── Pagination state ──────────────────────────────────────────────────────
    total_pages = max(1, (len(notifications) + PAGE_SIZE - 1) // PAGE_SIZE)

    if "notif_page" not in st.session_state:
        st.session_state["notif_page"] = 1

    # Clamp page if notifications were deleted
    if st.session_state["notif_page"] > total_pages:
        st.session_state["notif_page"] = total_pages

    current_page = st.session_state["notif_page"]
    start = (current_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_notifications = notifications[start:end]

    # ── Render current page ───────────────────────────────────────────────────
    for notif in page_notifications:
        n_id = notif["id"]
        summary = notif["summary"]
        created = notif["created_at"]

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
                # Support both old key names (holdings_movement) and new (holdings_moves)
                movements = summary.get("holdings_movement", summary.get("holdings_moves", []))
                show_account_col = (
                    get_setting("has_multiple_accounts", "false") == "true"
                    or len(get_known_accounts()) > 1
                )
                if movements:
                    st.markdown("**📈 Holdings Movement**")
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

                # Support both old key name (watchlist_changes) and new (watchlist_moves)
                changes = summary.get("watchlist_changes", summary.get("watchlist_moves", []))
                if changes:
                    st.markdown("**👀 Watchlist Changes**")
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
                    st.markdown("**📅 Upcoming Earnings**")
                    for e in earnings:
                        st.markdown(f"- {e['ticker']} — {e['date']}")

                if not movements and not changes and not earnings:
                    st.caption("No significant changes at time of launch.")

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

    # ── Page number buttons ───────────────────────────────────────────────────
    if total_pages > 1:
        st.divider()
        st.caption(f"Page {current_page} of {total_pages} — {len(notifications)} total notifications")
        cols = st.columns(min(total_pages, 10))
        for i, col in enumerate(cols):
            page_num = i + 1
            if page_num <= total_pages:
                label = f"**{page_num}**" if page_num == current_page else str(page_num)
                if col.button(label, key=f"page_btn_{page_num}"):
                    st.session_state["notif_page"] = page_num
                    st.rerun()