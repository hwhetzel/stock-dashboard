import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "portfolio.db")


def get_connection():
    """Return a sqlite3 connection with foreign keys enforced."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
    """Create all tables if they don't already exist, and run migrations."""
    conn = get_connection()
    c = conn.cursor()

    # --- Transactions ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker      TEXT    NOT NULL,
            type        TEXT    NOT NULL CHECK(type IN ('buy','sell')),
            shares      REAL    NOT NULL CHECK(shares > 0),
            price       REAL    NOT NULL CHECK(price > 0),
            date        TEXT    NOT NULL,
            notes       TEXT,
            account     TEXT,           -- e.g. "Doug's IRA", "Amy's IRA"
            source      TEXT    NOT NULL DEFAULT 'manual'  -- 'manual' or 'csv_import'
        )
    """)

    # --- Watchlist ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL UNIQUE,
            target_price    REAL,
            notes           TEXT,
            added_date      TEXT    NOT NULL
        )
    """)

    # --- Notifications ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    NOT NULL,
            summary     TEXT    NOT NULL,
            read        INTEGER NOT NULL DEFAULT 0
        )
    """)

    # --- Settings ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL
        )
    """)

    # --- Portfolio Snapshots ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL UNIQUE,
            value       REAL    NOT NULL,
            cost_basis  REAL    NOT NULL
    )
""")

    # --- Screener configs ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS screener_configs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            weights     TEXT    NOT NULL
        )
    """)

    # --- Archived Positions ---
    c.execute("""
        CREATE TABLE IF NOT EXISTS archived_positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL UNIQUE,
            archived_date   TEXT    NOT NULL,
            realized_gl     REAL    NOT NULL,
            notes           TEXT
        )
    """)

    conn.commit()

    # ── Migrations: add columns to existing DBs that predate this schema ──────
    # These are safe to run on a fresh DB too — they only fire if the column
    # doesn't already exist.
    existing_cols = [
        row[1] for row in c.execute("PRAGMA table_info(transactions)").fetchall()
    ]
    if "account" not in existing_cols:
        c.execute("ALTER TABLE transactions ADD COLUMN account TEXT")
    if "source" not in existing_cols:
        c.execute(
            "ALTER TABLE transactions ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        )

    conn.commit()
    conn.close()


# ── Transactions ─────────────────────────────────────────────────────────────

def add_transaction(ticker, type_, shares, price, date, notes="", account=None, source="manual"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO transactions (ticker, type, shares, price, date, notes, account, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker.upper(), type_, shares, price, date, notes, account, source)
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


def update_transaction(transaction_id, ticker, type_, shares, price, date, notes="", account=None):
    conn = get_connection()
    conn.execute(
        """UPDATE transactions
           SET ticker=?, type=?, shares=?, price=?, date=?, notes=?, account=?
           WHERE id=?""",
        (ticker.upper(), type_, shares, price, date, notes, account, transaction_id)
    )
    conn.commit()
    conn.close()


def delete_csv_transactions():
    """Remove all CSV-imported transactions — used before re-importing."""
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE source = 'csv_import'")
    conn.commit()
    conn.close()


def get_known_accounts() -> list[str]:
    """Return distinct non-null account names from all transactions."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT DISTINCT account FROM transactions WHERE account IS NOT NULL ORDER BY account"
    ).fetchall()
    conn.close()
    return [r["account"] for r in rows]


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


# ── Portfolio Snapshots ───────────────────────────────────────────────────────

def upsert_portfolio_snapshot(date: str, value: float, cost_basis: float):
    """Insert today's snapshot, or replace it if one already exists for this date."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO portfolio_snapshots (date, value, cost_basis)
           VALUES (?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET value=excluded.value, cost_basis=excluded.cost_basis""",
        (date, value, cost_basis)
    )
    conn.commit()
    conn.close()


def get_portfolio_snapshots() -> list[dict]:
    """Return all snapshots ordered oldest to newest."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM portfolio_snapshots ORDER BY date ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_snapshot_count() -> int:
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
    conn.close()
    return count


# ── Archived Positions ────────────────────────────────────────────────────────

def archive_position(ticker: str, realized_gl: float, notes: str = ""):
    """Move a fully-sold ticker to the archive."""
    from datetime import date as dt
    conn = get_connection()
    conn.execute(
        """INSERT INTO archived_positions (ticker, archived_date, realized_gl, notes)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET
               archived_date=excluded.archived_date,
               realized_gl=excluded.realized_gl,
               notes=excluded.notes""",
        (ticker.upper(), dt.today().strftime("%Y-%m-%d"), realized_gl, notes)
    )
    conn.commit()
    conn.close()


def get_archived_positions() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM archived_positions ORDER BY archived_date DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def unarchive_position(ticker: str):
    """Remove ticker from archive — called when a new buy transaction is added."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM archived_positions WHERE ticker = ?", (ticker.upper(),)
    )
    conn.commit()
    conn.close()


def is_archived(ticker: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM archived_positions WHERE ticker = ?", (ticker.upper(),)
    ).fetchone()
    conn.close()
    return row is not None

def delete_transactions_for_ticker(ticker: str):
    """Delete all transactions for a given ticker."""
    conn = get_connection()
    conn.execute("DELETE FROM transactions WHERE ticker = ?", (ticker.upper(),))
    conn.commit()
    conn.close()


# ── Bootstrap ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    initialize_db()
    print(f"Database initialized at {DB_PATH}")