# Asset allocation: portfolio value grouped by asset kind + cash.
import pytest

from backend import portfolio
from backend.db import connect, store_price, upsert_asset


@pytest.fixture()
def conn():
    return connect(":memory:")


def _tx(conn, acc, asset, typ, date, qty, price):
    amount = qty * price if qty is not None else price
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,0,'EUR')",
        (acc, asset, typ, date, qty, price, amount))


def test_allocation_groups_by_kind_and_cash(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    stock = upsert_asset(conn, "AAPL", None, "stock", "EUR")
    etf = upsert_asset(conn, "VWCE", None, "etf", "EUR")
    coin = upsert_asset(conn, "BTC", "bitcoin", "crypto", "EUR")
    _tx(conn, acc, stock, "buy", "2024-01-02", 10, 100.0)
    _tx(conn, acc, etf, "buy", "2024-01-03", 5, 200.0)
    _tx(conn, acc, coin, "buy", "2024-01-04", 1, 500.0)
    _tx(conn, acc, None, "deposit", "2024-01-01", None, 250.0)
    for t, d, p in (("AAPL", "2024-06-30", 110.0), ("VWCE", "2024-06-30", 210.0),
                    ("BTC", "2024-06-30", 440.0)):
        store_price(conn, t, d, p, "EUR")
    conn.commit()

    a = portfolio.allocation(conn, acc, as_of="2024-06-30")
    # market: 1100 + 1050 + 440 = 2590; cash: 250 - 1000 - 1000 - 500 = -2250
    assert a["currency"] == "EUR"
    assert a["groups"]["stock"] == pytest.approx(1100.0)
    assert a["groups"]["etf"] == pytest.approx(1050.0)
    assert a["groups"]["crypto"] == pytest.approx(440.0)
    assert a["groups"]["cash"] == pytest.approx(-2250.0)
    assert a["total"] == pytest.approx(340.0)
    assert a["shares"]["stock"] == pytest.approx(1100.0 / 340.0, rel=1e-5)


def test_allocation_cash_only_account(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    _tx(conn, acc, None, "deposit", "2024-01-01", None, 1000.0)
    conn.commit()
    a = portfolio.allocation(conn, acc, as_of="2024-01-01")
    assert a["groups"] == {"cash": 1000.0}
    assert a["shares"] == {"cash": 1.0}


def test_allocation_missing_asset_row_defaults_to_stock(conn):
    # Transactions without an asset row (asset_id NULL) carry no ticker and
    # are invisible to allocation; only real assets + cash are grouped.
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    _tx(conn, acc, None, "deposit", "2024-01-01", None, 500.0)
    conn.commit()
    a = portfolio.allocation(conn, acc, as_of="2024-01-01")
    assert a["groups"] == {"cash": 500.0}
    assert a["shares"] == {"cash": 1.0}


def test_allocation_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "a.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    client.post("/api/transactions", json={
        "account_id": acc, "type": "deposit", "date": "2024-01-01",
        "amount": 500.0, "currency": "EUR"})
    client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "AAPL", "quantity": 5, "price": 50.0, "currency": "EUR"})
    client.post("/api/prices", params={
        "ticker": "AAPL", "date": "2024-06-30", "price": 60.0, "currency": "EUR"})
    r = client.get("/api/portfolio/allocation",
                   params={"account_id": acc, "as_of": "2024-06-30"})
    assert r.status_code == 200
    g = r.json()["groups"]
    assert g["stock"] == pytest.approx(300.0)
    assert g["cash"] == pytest.approx(250.0)
