# Extended asset classes: bond / metal / real_estate (manual valuation),
# including schema migration for DBs created before they existed.
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import prices as prices_mod
from backend import portfolio
from backend.db import connect, store_price, upsert_asset
from backend.main import app

NEW_KINDS = ["bond", "metal", "real_estate"]

# The assets schema as it was BEFORE the new classes were added.
OLD_ASSETS_DDL = """
CREATE TABLE assets (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker    TEXT NOT NULL UNIQUE,
    name      TEXT,
    kind      TEXT NOT NULL DEFAULT 'stock' CHECK (kind IN ('stock','etf','crypto','cash')),
    currency  TEXT NOT NULL DEFAULT 'USD'
);
"""


@pytest.fixture()
def conn(tmp_path):
    return connect(str(tmp_path / "kinds.db"))


def test_new_kinds_accepted(conn):
    for kind in NEW_KINDS:
        asset_id = upsert_asset(conn, kind.upper()[:4] + "1", None, kind, "EUR")
        assert asset_id > 0
    kinds = {r["ticker"]: r["kind"] for r in conn.execute("SELECT * FROM assets")}
    assert set(kinds.values()) >= set(NEW_KINDS)


def test_unknown_kind_still_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError):
        upsert_asset(conn, "XX", None, "diamonds", "EUR")


def test_migration_from_old_schema_preserves_rows_and_enables_new_kinds(tmp_path):
    path = str(tmp_path / "old.db")
    legacy = sqlite3.connect(path)
    legacy.executescript(OLD_ASSETS_DDL)
    legacy.execute("INSERT INTO assets(ticker, name, kind, currency) "
                   "VALUES ('OLD', 'Old stock', 'stock', 'EUR')")
    legacy.commit()
    legacy.close()

    conn = connect(path)  # migration runs on connect
    row = conn.execute("SELECT * FROM assets WHERE ticker='OLD'").fetchone()
    assert row["kind"] == "stock"
    # new kinds now accepted in the SAME file
    upsert_asset(conn, "GOLD", "Gold bars", "metal", "EUR")
    migrated_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='assets'"
    ).fetchone()["sql"]
    for kind in NEW_KINDS:
        assert kind in migrated_sql


def test_bond_end_to_end_valuation(conn):
    cur = conn.execute("INSERT INTO accounts(name, currency, cash) VALUES ('B','EUR',0)")
    acc = cur.lastrowid
    bond = upsert_asset(conn, "UA5Y", "5y bond", "bond", "EUR")
    for t, qty, price in (("2024-01-05", 2, 950.0),):
        conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
            " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
            (acc, bond, "buy", t, qty, price, None, 0.0, "EUR"))
    conn.execute("INSERT INTO transactions(account_id, asset_id, type, date,"
                 " quantity, price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
                 (acc, None, "deposit", "2024-01-01", None, None, 3000.0, 0.0, "EUR"))
    store_price(conn, "UA5Y", "2024-02-01", 980.0, "EUR")
    val = portfolio.value_on_date(conn, acc, "2024-02-01")
    assert val["market"] == 1960.0          # 2 * 980
    assert val["cash"] == 1100.0            # 3000 - 1900
    assert val["total"] == 3060.0


def test_update_prices_skips_manual_kinds(conn, monkeypatch):
    upsert_asset(conn, "GOLD", "Gold", "metal", "USD")

    def _boom(symbol):
        raise AssertionError("no fetch for manual asset classes")

    monkeypatch.setattr(prices_mod, "fetch_stooq_latest", _boom)
    results = prices_mod.update_prices(conn, ["GOLD"])
    assert results == {"GOLD": None}


def test_backfill_rejects_manual_kinds(conn):
    upsert_asset(conn, "FLAT", "Apartment", "real_estate", "EUR")
    out = prices_mod.backfill_prices(conn, "FLAT", "2024-01-01", "2024-01-31")
    assert out["stored"] == 0 and "manual" in out["error"]


def test_allocation_groups_new_kinds(conn):
    cur = conn.execute("INSERT INTO accounts(name, currency, cash) VALUES ('A','EUR',0)")
    acc = cur.lastrowid
    metal = upsert_asset(conn, "GOLD", "Gold", "metal", "EUR")
    conn.execute("INSERT INTO transactions(account_id, asset_id, type, date,"
                 " quantity, price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
                 (acc, metal, "buy", "2024-01-01", 1, 100.0, None, 0.0, "EUR"))
    conn.execute("INSERT INTO transactions(account_id, asset_id, type, date,"
                 " quantity, price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
                 (acc, None, "deposit", "2024-01-01", None, None, 220.0, 0.0, "EUR"))
    store_price(conn, "GOLD", "2024-01-02", 120.0, "EUR")
    alloc = portfolio.allocation(conn, acc, "2024-01-02")
    assert alloc["groups"]["metal"] == 120.0
    assert alloc["groups"]["cash"] == 120.0   # 220 deposit - 100 buy


def test_api_transaction_with_explicit_kind(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "api.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "A", "currency": "EUR"}).json()["id"]
    r = client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "UA5Y", "quantity": 1, "price": 950, "currency": "EUR",
        "kind": "bond"})
    assert r.status_code == 200
    assets = client.get("/api/assets").json()
    kinds = {a["ticker"]: a["kind"] for a in assets}
    assert kinds["UA5Y"] == "bond"


def test_csv_import_kind_bond():
    from backend.csv_import import parse_csv
    rows = parse_csv("date,ticker,action,quantity,price,currency,kind\n"
                     "2024-01-01,UA5Y,buy,2,950,EUR,bond\n")
    assert rows[0]["kind"] == "bond"
