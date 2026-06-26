import streamlit as st
from datetime import datetime
from database import get_transactions, get_watchlist, get_setting, get_known_accounts
import yfinance as yf
from streamlit_autorefresh import st_autorefresh 


def check_price_thresholds() -> list[dict]:
    """
    Check current prices against notification thresholds.
    Returns list of alerts with ticker, price, change_pct, threshold_type.
    """
    price_threshold = float(str(get_setting("notify_price_change_pct", "2.0")))
    watch_threshold = float(str(get_setting("notify_watchlist_change_pct", "1.0")))
    notify_holdings_on = get_setting("notify_holdings", "1") == "1"
    notify_watchlist_on = get_setting("notify_watchlist", "1") == "1"

    # Build held tickers
    transactions = get_transactions()
    by_ticker: dict = {}
    for tx in sorted(transactions, key=lambda x: x["date"]):
        by_ticker.setdefault(tx["ticker"], []).append(tx)

    held_tickers = []
    for ticker, txs in by_ticker.items():
        shares = 0.0
        for tx in txs:
            if tx["type"] == "buy":
                shares += tx["shares"]
            elif tx["type"] == "sell":
                shares -= tx["shares"]
        if shares > 0.0001:
            held_tickers.append(ticker)

    watchlist = get_watchlist()
    watch_tickers = [w["ticker"] for w in watchlist]

    alerts = []

    # Check holdings
    if notify_holdings_on:
        for ticker in held_tickers:
            # Skip if we already alerted this ticker recently this session
            last_alert_key = f"price_alert_last_{ticker}"
            last_alert = st.session_state.get(last_alert_key)
            if last_alert:
                minutes_since = (datetime.now() - last_alert).total_seconds() / 60
                check_interval = float(str(get_setting("idle_check_interval_mins", "5")))
                if minutes_since < check_interval:
                    continue

            try:
                fi = yf.Ticker(ticker).fast_info
                current = fi.last_price
                prev = fi.previous_close
                if current and prev and prev > 0:
                    change_pct = (current - prev) / prev * 100
                    if abs(change_pct) >= price_threshold:
                        alerts.append({
                            "ticker": ticker,
                            "price": round(current, 2),
                            "change_pct": round(change_pct, 2),
                            "threshold_type": "Holdings Movement",
                        })
                        st.session_state[last_alert_key] = datetime.now()
            except Exception:
                pass

    # Check watchlist
    if notify_watchlist_on:
        for ticker in watch_tickers:
            last_alert_key = f"price_alert_last_{ticker}"
            last_alert = st.session_state.get(last_alert_key)
            if last_alert:
                minutes_since = (datetime.now() - last_alert).total_seconds() / 60
                check_interval = float(str(get_setting("idle_check_interval_mins", "5")))
                if minutes_since < check_interval:
                    continue

            try:
                fi = yf.Ticker(ticker).fast_info
                current = fi.last_price
                prev = fi.previous_close
                if current and prev and prev > 0:
                    change_pct = (current - prev) / prev * 100
                    if abs(change_pct) >= watch_threshold:
                        alerts.append({
                            "ticker": ticker,
                            "price": round(current, 2),
                            "change_pct": round(change_pct, 2),
                            "threshold_type": "Watchlist Change",
                        })
                        st.session_state[last_alert_key] = datetime.now()
            except Exception:
                pass

    return alerts


def fire_desktop_alerts(alerts: list[dict]):
    """Fire plyer desktop popup for each alert."""
    if not alerts:
        return
    try:
        import subprocess, sys
        for alert in alerts:
            sign = "+" if alert["change_pct"] >= 0 else ""
            message = (
                f"{alert['ticker']} ${alert['price']} "
                f"({sign}{alert['change_pct']}%) — {alert['threshold_type']}"
            )
            script = (
                "from plyer import notification; "
                f"notification.notify(title='Stock Dashboard Alert', "
                f"message={repr(message)}, "
                f"app_name='Stock Dashboard', "
                f"timeout=10)"
            )
            subprocess.Popen([sys.executable, "-c", script])
    except Exception:
        pass


def run_idle_monitor():
    """
    Inject idle detection JS and run autorefresh when idle.
    Call this at the top of every page after apply_theme().
    Only fires price checks and popups when delivery is set to desktop
    and auto-refresh is enabled in settings.
    """
    # Check if feature is enabled
    if get_setting("idle_monitor_enabled", "0") != "1":
        return
    if get_setting("notify_delivery", "app") != "desktop":
        return

    idle_timeout_mins = float(str(get_setting("idle_timeout_mins", "5")))
    check_interval_mins = float(str(get_setting("idle_check_interval_mins", "5")))
    idle_timeout_ms = int(idle_timeout_mins * 60 * 1000)

    # Inject JS to track user activity and set a cookie/flag when idle
    import streamlit.components.v1 as components
    components.html(
        f"""
        <script>
        let idleTimer;
        let isIdle = false;

        function resetTimer() {{
            clearTimeout(idleTimer);
            isIdle = false;
            window.parent.postMessage({{type: 'idle', value: false}}, '*');
            idleTimer = setTimeout(() => {{
                isIdle = true;
                window.parent.postMessage({{type: 'idle', value: true}}, '*');
            }}, {idle_timeout_ms});
        }}

        document.addEventListener('mousemove', resetTimer);
        document.addEventListener('keypress', resetTimer);
        document.addEventListener('click', resetTimer);
        document.addEventListener('scroll', resetTimer);
        resetTimer();
        </script>
        """,
        height=0,
    )

    # Track idle state in session state
    if "is_idle" not in st.session_state:
        st.session_state["is_idle"] = False

    # Use autorefresh when idle — interval matches check interval setting
    if st.session_state.get("is_idle", False):
        st_autorefresh(
            interval=int(check_interval_mins * 60 * 1000),
            key="idle_autorefresh",
        )
        # Run price checks and fire alerts
        alerts = check_price_thresholds()
        if alerts:
            fire_desktop_alerts(alerts)