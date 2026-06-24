import re
import json
import pandas as pd
from typing import Optional
from datetime import date as dt, datetime as dt_datetime
from database import (
    add_transaction,
    delete_csv_transactions,
    get_transactions,
    remove_from_watchlist,
    get_watchlist,
    add_notification,
    set_setting,
    get_setting,
)


def _clean_num(val) -> Optional[float]:
    """Strip $, commas, spaces, % from a value and return float, or None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).replace("$", "").replace(",", "").replace("%", "").replace(" ", "").strip()
    if s in ("", "-", "N/A", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_open_date(val) -> str:
    """
    Return YYYY-MM-DD if val is a real date, else today's date.
    Ameriprise uses 'Multiple' when a position has more than one lot.
    """
    today = dt.today().strftime("%Y-%m-%d")
    if not val or str(val).strip().lower() in ("multiple", "n/a", "", "nan"):
        return today
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return dt_datetime.strptime(str(val).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return today


def parse_unrealized_gl_csv(filepath_or_buffer) -> list:
    """
    Parse Ameriprise PortfolioUnrealizedGainLoss CSV.

    The file has summary header rows before the actual data.
    We scan for the header row containing 'Symbol' and read from there.
    Returns a list of dicts, one per position row.
    """
    # Read all rows as raw strings to find where real data starts
    raw = pd.read_csv(filepath_or_buffer, header=None, dtype=str)

    # Find the row index where 'Symbol' appears in column 0
    header_row = None
    for i, row in raw.iterrows():
        if str(row.iloc[0]).strip().lower() == "symbol":
            header_row = i
            break

    if header_row is None:
        raise ValueError(
            "Could not find 'Symbol' header row in CSV. "
            "Make sure you're uploading the Unrealized Gain/Loss export."
        )

    # Seek back to start if buffer (Streamlit UploadedFile), else re-read path
    # raw used up the buffer — we must reset before reading again
    assert isinstance(header_row, int)

    if hasattr(filepath_or_buffer, "seek"):
        filepath_or_buffer.seek(0)

    df = pd.read_csv(filepath_or_buffer, header=header_row, dtype=str)

    # Normalize column names
    df.columns = [str(c).strip() for c in df.columns]

    # Drop rows where Symbol is blank, a section header, or "Total"
    df = df[df["Symbol"].notna()]
    df = df[~df["Symbol"].str.strip().str.lower().isin(
        ["symbol", "total", "equities", "mutual funds & uits", ""]
    )]
    df = df[~df["Symbol"].str.startswith("Total", na=False)]

    positions = []
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        if not symbol or symbol in ("NAN", ""):
            continue

        account = str(row.get("Account Name", row.get("Account", ""))).strip()
        if account.lower() in ("nan", ""):
            account = None

        quantity = _clean_num(row.get("Quantity", row.get("Shares", None)))
        unit_price = _clean_num(row.get("Unit Cost", row.get("Unit Price", None)))
        cost_basis = _clean_num(row.get("Total Cost", row.get("Cost Basis", None)))
        open_date = _parse_open_date(row.get("Open Date", row.get("Date Acquired", None)))
        mkt_price = _clean_num(row.get("Mkt. Price", row.get("Market Price", None)))

        if quantity is None or quantity <= 0:
            continue

        # Derive unit price from cost basis if unit price column missing
        if unit_price is None and cost_basis is not None and quantity:
            unit_price = cost_basis / quantity

        # Fall back to market price if no cost info at all
        if unit_price is None:
            unit_price = mkt_price

        if unit_price is None or unit_price <= 0:
            continue

        positions.append({
            "symbol": symbol,
            "quantity": quantity,
            "unit_price": unit_price,
            "cost_basis": cost_basis,
            "open_date": open_date,
            "account": account,
            "mkt_price": mkt_price,
        })

    return positions


def detect_changes(new_positions: list) -> dict:
    """
    Compare new_positions against the last saved CSV snapshot stored in settings.
    Returns a dict describing what changed.
    """
    # Fix: get_setting returns None when key doesn't exist, not "[]"
    snapshot_raw = get_setting("csv_import_snapshot", None)
    try:
        old_positions = json.loads(snapshot_raw) if snapshot_raw else []
    except Exception:
        old_positions = []

    old_map = {p["symbol"]: p for p in old_positions}
    new_map = {p["symbol"]: p for p in new_positions}

    added = []
    removed = []
    changed = []

    for sym, new in new_map.items():
        if sym not in old_map:
            added.append(sym)
        else:
            old = old_map[sym]
            share_diff = round((new["quantity"] or 0) - (old["quantity"] or 0), 6)
            price_diff = round(
                (new["unit_price"] or 0) - (old["unit_price"] or 0), 4
            )
            if abs(share_diff) > 0.0001 or abs(price_diff) > 0.001:
                changed.append({
                    "symbol": sym,
                    "old_shares": old["quantity"],
                    "new_shares": new["quantity"],
                    "share_diff": share_diff,
                    "old_unit_price": old["unit_price"],
                    "new_unit_price": new["unit_price"],
                })

    for sym in old_map:
        if sym not in new_map:
            removed.append(sym)

    return {"added": added, "removed": removed, "changed": changed}


def apply_csv_import(positions: list) -> dict:
    """
    Main import function:
    1. Detects changes vs last import
    2. Removes old csv_import transactions
    3. Inserts new synthetic buy transactions
    4. Auto-removes imported tickers from watchlist
    5. Saves new snapshot + import date to settings
    6. Saves a notification summary
    7. Updates has_multiple_accounts setting
    Returns the change summary dict.
    """
    today = dt.today().strftime("%Y-%m-%d")

    changes = detect_changes(positions)

    delete_csv_transactions()

    accounts = set(p["account"] for p in positions if p["account"])
    has_multiple = len(accounts) > 1
    set_setting("has_multiple_accounts", "true" if has_multiple else "false")

    imported_tickers = []
    for p in positions:
        note_parts = []
        if p["account"]:
            note_parts.append(p["account"])
        note_parts.append("CSV import")
        raw_open = p.get("open_date", today)
        if raw_open == today:
            note_parts.append("multiple open dates — date approximated")
        else:
            note_parts.append(f"open date {raw_open}")
        notes = " — ".join(note_parts)

        add_transaction(
            ticker=p["symbol"],
            type_="buy",
            shares=p["quantity"],
            price=p["unit_price"],
            date=p.get("open_date", today),
            notes=notes,
            account=p["account"],
            source="csv_import",
        )
        imported_tickers.append(p["symbol"])

    watchlist = get_watchlist()
    watchlist_tickers = {w["ticker"] for w in watchlist}
    moved_from_watchlist = []
    for ticker in imported_tickers:
        if ticker in watchlist_tickers:
            remove_from_watchlist(ticker)
            moved_from_watchlist.append(ticker)

    set_setting("csv_import_snapshot", json.dumps(positions))
    set_setting("last_csv_import", today)

    summary = {
        "type": "csv_import",
        "date": today,
        "total_positions": len(positions),
        "added": changes["added"],
        "removed": changes["removed"],
        "changed": changes["changed"],
        "moved_from_watchlist": moved_from_watchlist,
        "accounts": sorted(accounts),
    }
    add_notification(summary)

    return summary