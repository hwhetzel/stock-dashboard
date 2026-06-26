import yfinance as yf
from datetime import datetime, timedelta
from database import (
    get_transactions,
    get_watchlist,
    get_setting,
    add_notification,
)


def _get_held_tickers() -> list[str]:
    """Return list of currently held tickers from transactions."""
    transactions = get_transactions()
    by_ticker: dict = {}
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


def _check_holdings_movement(held_tickers: list[str], threshold: float) -> list[dict]:
    """Check holdings for price movement above threshold."""
    alerts = []
    for ticker in held_tickers:
        try:
            fi = yf.Ticker(ticker).fast_info
            current = fi.last_price
            prev = fi.previous_close
            if current and prev and prev > 0:
                change_pct = (current - prev) / prev * 100
                if abs(change_pct) >= threshold:
                    alerts.append({
                        "ticker": ticker,
                        "price": round(current, 2),
                        "change_pct": round(change_pct, 2),
                        "threshold_type": "Holdings Movement",
                    })
        except Exception:
            pass
    return alerts


def _check_watchlist_movement(watchlist: list[dict], threshold: float) -> list[dict]:
    """Check watchlist for price movement above threshold."""
    alerts = []
    for w in watchlist:
        ticker = w["ticker"]
        try:
            fi = yf.Ticker(ticker).fast_info
            current = fi.last_price
            prev = fi.previous_close
            if current and prev and prev > 0:
                change_pct = (current - prev) / prev * 100
                if abs(change_pct) >= threshold:
                    alerts.append({
                        "ticker": ticker,
                        "price": round(current, 2),
                        "change_pct": round(change_pct, 2),
                        "threshold_type": "Watchlist Change",
                    })
        except Exception:
            pass
    return alerts


def _check_upcoming_earnings(all_tickers: list[str], lead_days: int) -> list[dict]:
    """Check for upcoming earnings within lead_days."""
    from data import get_earnings_dates
    alerts = []
    now = datetime.now()
    deadline = now + timedelta(days=lead_days)
    for ticker in all_tickers:
        try:
            df = get_earnings_dates(ticker, limit=4)
            if df.empty:
                continue
            for dt_idx in df.index:
                dt_naive = dt_idx.tz_localize(None) if dt_idx.tzinfo else dt_idx
                if now <= dt_naive <= deadline:
                    days_away = (dt_naive - now).days
                    alerts.append({
                        "ticker": ticker,
                        "date": dt_naive.strftime("%Y-%m-%d"),
                        "days_away": days_away,
                        "threshold_type": "Upcoming Earnings",
                    })
        except Exception:
            pass
    return alerts


def _check_upcoming_dividends(held_tickers: list[str], lead_days: int) -> list[dict]:
    """Check for upcoming ex-dividend dates within lead_days."""
    alerts = []
    now = datetime.now()
    deadline = now + timedelta(days=lead_days)
    for ticker in held_tickers:
        try:
            info = yf.Ticker(ticker).info
            ex_div = info.get("exDividendDate")
            if ex_div:
                ex_div_dt = datetime.fromtimestamp(ex_div)
                if now <= ex_div_dt <= deadline:
                    days_away = (ex_div_dt - now).days
                    alerts.append({
                        "ticker": ticker,
                        "date": ex_div_dt.strftime("%Y-%m-%d"),
                        "days_away": days_away,
                        "threshold_type": "Upcoming Ex-Dividend",
                    })
        except Exception:
            pass
    return alerts


def run_background_checks() -> list[dict]:
    """
    Run all threshold checks.
    Called by the background thread in launcher.py.
    Returns list of alert dicts.
    """
    # Check if background alerts are enabled
    if get_setting("price_alerts_enabled", "0") != "1":
        return []

    price_threshold = float(str(get_setting("notify_price_change_pct", "2.0")))
    watch_threshold = float(str(get_setting("notify_watchlist_change_pct", "1.0")))
    earnings_lead = int(str(get_setting("notify_earnings_lead_days", "7")))
    dividend_lead = int(str(get_setting("notify_dividend_lead_days", "7")))
    notify_holdings_on = get_setting("notify_holdings", "1") == "1"
    notify_watchlist_on = get_setting("notify_watchlist", "1") == "1"
    notify_earnings_on = get_setting("notify_earnings", "1") == "1"
    notify_dividends_on = get_setting("notify_dividends", "1") == "1"

    held_tickers = _get_held_tickers()
    watchlist = get_watchlist()
    watch_tickers = [w["ticker"] for w in watchlist]
    all_tickers = list(dict.fromkeys(held_tickers + watch_tickers))

    alerts = []

    if notify_holdings_on and held_tickers:
        alerts += _check_holdings_movement(held_tickers, price_threshold)

    if notify_watchlist_on and watchlist:
        alerts += _check_watchlist_movement(watchlist, watch_threshold)

    if notify_earnings_on and all_tickers:
        alerts += _check_upcoming_earnings(all_tickers, earnings_lead)

    if notify_dividends_on and held_tickers:
        alerts += _check_upcoming_dividends(held_tickers, dividend_lead)

    return alerts


def fire_alerts(alerts: list[dict]):
    """
    Save alerts to notifications DB and fire plyer desktop popup.
    Called by background thread after run_background_checks().
    """
    if not alerts:
        return

    # Save to notifications DB
    from datetime import datetime
    summary = {
        "type": "price_alert",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "alerts": alerts,
    }
    add_notification(summary)

    # Fire desktop popup if delivery method is set to desktop
    if get_setting("notify_delivery", "app") != "desktop":
        return

    try:
        import subprocess, sys
        # Build message — max 3 alerts in popup to keep it readable
        lines = []
        for a in alerts[:3]:
            if a["threshold_type"] in ("Holdings Movement", "Watchlist Change"):
                sign = "+" if a["change_pct"] >= 0 else ""
                lines.append(
                    f"{a['ticker']} ${a['price']} ({sign}{a['change_pct']}%) — {a['threshold_type']}"
                )
            elif a["threshold_type"] in ("Upcoming Earnings", "Upcoming Ex-Dividend"):
                lines.append(
                    f"{a['ticker']} — {a['threshold_type']} in {a['days_away']} day(s)"
                )
        if len(alerts) > 3:
            lines.append(f"...and {len(alerts) - 3} more")
        message = "\n".join(lines)

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