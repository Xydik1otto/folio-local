# First-run demo data: opt-in "Load demo data" button creates a sample account.
from __future__ import annotations

import datetime as dt

from .db import connect, upsert_asset

DEMO_ACCOUNT = "Demo"

# (type, days_ago, ticker, kind, currency, quantity, price, amount, fees)
DEMO_ROWS = [
    ("deposit",    400, None,  None,    "EUR", None, None, 5000.0, 0.0),
    ("buy",        380, "AAPL", "stock", "USD", 10,  185.0, None,   1.0),
    ("buy",        350, "MSFT", "stock", "USD",  5,  400.0, None,   1.0),
    ("buy",        320, "VWCE", "etf",   "EUR", 20,  110.0, None,   1.5),
    ("buy",        200, "BTC",  "crypto","USD", 0.1, 60000.0, None, 2.0),
    ("dividend",   150, "AAPL", "stock", "USD", None, None, 24.0,  0.0),
    ("sell",        90, "MSFT", "stock", "USD",  2,  420.0, None,   1.0),
    ("dividend",    60, "VWCE", "etf",   "EUR", None, None, 31.0,  0.0),
    ("buy",         30, "KO",   "stock", "USD", 15,   62.0, None,   1.0),
    ("deposit",      7, None,  None,    "EUR", None, None, 1000.0, 0.0),
]


def demo_data_exists(conn) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM accounts WHERE name = ?", (DEMO_ACCOUNT,)).fetchone())


def load_demo_data(db_path: str) -> int:
    """Create the «Demo» account with sample transactions.

    Returns the number of transactions created. Idempotent: if a Demo account
    already exists, nothing is created (returns 0).
    """
    conn = connect(db_path)
    try:
        if demo_data_exists(conn):
            return 0
        with conn:
            acc = conn.execute(
                "INSERT INTO accounts(name, currency, cash) VALUES (?,?,?)",
                (DEMO_ACCOUNT, "EUR", 0.0)).lastrowid
            today = dt.date.today()
            for (typ, days_ago, ticker, kind, cur,
                 qty, price, amount, fees) in DEMO_ROWS:
                day = (today - dt.timedelta(days=days_ago)).isoformat()
                asset_id = None
                if ticker:
                    asset_id = upsert_asset(conn, ticker, None, kind, cur)
                conn.execute(
                    "INSERT INTO transactions(account_id, asset_id, type, date,"
                    " quantity, price, amount, fees, currency)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (acc, asset_id, typ, day, qty, price, amount, fees, cur))
        conn.close()
        return len(DEMO_ROWS)
    except Exception:
        conn.close()
        raise
