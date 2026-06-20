import sqlite3
import os

# Always resolve the db path relative to this file's location,
# so the app works regardless of where it's launched from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "portfolio.db")


def get_connection():
    """Return a sqlite3 connection with foreign keys enforced."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    return conn


def initialize_db():
    """Create all tables if they don't already exist."""
    conn = get_connection()
    c = conn.cursor()

    # --- Transactions ---
    # One row per buy/sell event. Holdings are calculated from these.
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            type        TEXT    NOT NULL CHECK(type IN ('buy','sell')),
            shares      REAL    NOT NULL CHECK(shares > 0),
            price       REAL    NOT NULL CHECK(price > 0),
            date        TEXT    NOT NULL,  -- stored as YYYY-MM-DD string
            notes       TEXT
        )
    """)

    # --- Watchlist ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL UNIQUE,
            target_price    REAL,           -- optional alert price
            notes           TEXT,
            added_date      TEXT    NOT NULL
        )
    """)

    # --- Notifications ---
    # Each row is a session summary generated on app open or CSV import.
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,  -- YYYY-MM-DD HH:MM:SS
            summary     TEXT    NOT NULL,  -- full summary text (JSON string)
            read        INTEGER NOT NULL DEFAULT 0  -- 0 = unread, 1 = read
        )
    """)

    # --- Settings ---
    # Key-value store for all user preferences.
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        )
    """)

    # --- Screener configs ---
    # Saves named screener weight profiles so the user can reuse them.
    c.execute("""
        CREATE TABLE IF NOT EXISTS screener_configs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            weights     TEXT    NOT NULL   -- JSON string of weight dict
        )
    """)

    conn.commit()
    conn.close()


# ── Transactions ─────────────────────────────────────────────────────────────

def add_transaction(ticker, type_, shares, price, date, notes=""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO transactions (ticker, type, shares, price, date, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (ticker.upper(), type_, shares, price, date, notes)
    )
    conn.commit()
    conn.close()


def get_transactions(ticker=None):
    """Return all transactions, or filter by ticker."""
    conn = get_connection()
    if ticker:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE ticker = ? ORDER BY date DESC",
            (ticker.upper(),)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM transactions ORDER BY date DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_transaction(transaction_id):
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    conn.commit()
    conn.close()


def update_transaction(transaction_id, ticker, type_, shares, price, date, notes=""):
    conn = get_connection()
    conn.execute(
        """UPDATE transactions
           SET ticker=?, type=?, shares=?, price=?, date=?, notes=?
           WHERE id=?""",
        (ticker.upper(), type_, shares, price, date, notes, transaction_id)
    )
    conn.commit()
    conn.close()


# ── Watchlist ─────────────────────────────────────────────────────────────────

def add_to_watchlist(ticker, target_price=None, notes="", added_date=None):
    from datetime import date as dt
    if added_date is None:
        added_date = dt.today().strftime("%Y-%m-%d")
    conn = get_connection()
    conn.execute(
        """INSERT OR IGNORE INTO watchlist (ticker, target_price, notes, added_date)
           VALUES (?, ?, ?, ?)""",
        (ticker.upper(), target_price, notes, added_date)
    )
    conn.commit()
    conn.close()


def get_watchlist():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM watchlist ORDER BY ticker").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_from_watchlist(ticker):
    conn = get_connection()
    conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    conn.close()


def update_watchlist_item(ticker, target_price=None, notes=""):
    conn = get_connection()
    conn.execute(
        "UPDATE watchlist SET target_price=?, notes=? WHERE ticker=?",
        (target_price, notes, ticker.upper())
    )
    conn.commit()
    conn.close()


# ── Screener configs ──────────────────────────────────────────────────────────

def save_screener_config(name, weights: dict):
    import json
    conn = get_connection()
    conn.execute(
        """INSERT INTO screener_configs (name, weights)
           VALUES (?, ?)
           ON CONFLICT(name) DO UPDATE SET weights=excluded.weights""",
        (name, json.dumps(weights))
    )
    conn.commit()
    conn.close()


def get_screener_configs():
    import json
    conn = get_connection()
    rows = conn.execute("SELECT * FROM screener_configs").fetchall()
    conn.close()
    return {r["name"]: json.loads(r["weights"]) for r in rows}


def delete_screener_config(name):
    conn = get_connection()
    conn.execute("DELETE FROM screener_configs WHERE name = ?", (name,))
    conn.commit()
    conn.close()

# ── Notifications ─────────────────────────────────────────────────────────────

def add_notification(summary: dict):
    """Save a new session summary notification."""
    import json
    from datetime import datetime
    conn = get_connection()
    conn.execute(
        "INSERT INTO notifications (created_at, summary, read) VALUES (?, ?, 0)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(summary))
    )
    conn.commit()
    conn.close()


def get_notifications() -> list[dict]:
    """Return all notifications newest first."""
    import json
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM notifications ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["summary"] = json.loads(d["summary"])
        result.append(d)
    return result


def mark_notification_read(notification_id: int):
    conn = get_connection()
    conn.execute("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def mark_all_notifications_read():
    conn = get_connection()
    conn.execute("UPDATE notifications SET read = 1")
    conn.commit()
    conn.close()


def delete_notification(notification_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
    conn.commit()
    conn.close()


def delete_notifications(ids: list[int]):
    conn = get_connection()
    conn.executemany("DELETE FROM notifications WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()


def delete_all_notifications():
    conn = get_connection()
    conn.execute("DELETE FROM notifications")
    conn.commit()
    conn.close()


def get_unread_count() -> int:
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE read = 0"
    ).fetchone()[0]
    conn.close()
    return count


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value):
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value))
    )
    conn.commit()
    conn.close()

# ── Bootstrap ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    initialize_db()
    print(f"Database initialized at {DB_PATH}")