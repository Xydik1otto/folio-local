# SQLite schema + connection helpers (stdlib sqlite3, no ORM dependency)
import os
import sqlite3

DB_PATH = os.environ.get("FOLIO_DB", os.path.join(os.path.dirname(__file__), "..", "folio.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    currency  TEXT NOT NULL DEFAULT 'EUR',
    cash      REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assets (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker    TEXT NOT NULL UNIQUE,
    name      TEXT,
    kind      TEXT NOT NULL DEFAULT 'stock' CHECK (kind IN ('stock','etf','crypto','cash')),
    currency  TEXT NOT NULL DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS transactions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    asset_id   INTEGER REFERENCES assets(id),
    type       TEXT NOT NULL CHECK (type IN ('buy','sell','dividend','fee','deposit','withdrawal')),
    date       TEXT NOT NULL,
    quantity   REAL,
    price      REAL,
    amount     REAL,
    fees       REAL NOT NULL DEFAULT 0,
    currency   TEXT NOT NULL DEFAULT 'EUR',
    note       TEXT
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker   TEXT NOT NULL,
    date     TEXT NOT NULL,
    price    REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    UNIQUE (ticker, date, currency)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    date     TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate_to_eur REAL NOT NULL,
    PRIMARY KEY (date, currency)
);
"""

# FX rate on/just before a transaction date: currency -> EUR.
# EUR itself is 1.0 always.


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    conn.commit()
    return conn


# --- small repository helpers ------------------------------------------------

def get_asset(conn, ticker: str):
    return conn.execute("SELECT * FROM assets WHERE ticker = ?", (ticker,)).fetchone()


def upsert_asset(conn, ticker: str, name: str | None = None,
                 kind: str = "stock", currency: str = "USD") -> int:
    row = get_asset(conn, ticker)
    if row:
        return row["id"]
    with conn:
        cur = conn.execute(
            "INSERT INTO assets(ticker, name, kind, currency) VALUES (?,?,?,?)",
            (ticker, name, kind, currency),
        )
    return cur.lastrowid


def store_price(conn, ticker: str, date: str, price: float, currency: str = "USD") -> None:
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO price_snapshots(ticker, date, price, currency) "
            "VALUES (?,?,?,?)",
            (ticker, date, price, currency),
        )


def latest_price(conn, ticker: str, as_of: str | None = None):
    """Most recent snapshot with date <= as_of (default: latest overall)."""
    if as_of:
        return conn.execute(
            "SELECT * FROM price_snapshots WHERE ticker = ? AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            (ticker, as_of),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM price_snapshots WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,),
    ).fetchone()


def account_transactions(conn, account_id: int):
    return conn.execute(
        "SELECT t.*, a.ticker, a.kind AS asset_kind, a.currency AS asset_currency "
        "FROM transactions t LEFT JOIN assets a ON a.id = t.asset_id "
        "WHERE t.account_id = ? ORDER BY t.date, t.id",
        (account_id,),
    ).fetchall()
