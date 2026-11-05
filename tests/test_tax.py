# Tax report preview: realized gains per year via FIFO or LIFO lot matching.
import pytest

from backend import portfolio
from backend.db import connect, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


def _tx(conn, acc, asset, typ, date, qty, price, fees=0.0, ccy="EUR"):
    amount = qty * price if qty is not None else price
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
        (acc, asset, typ, date, qty, price, amount, fees, ccy))


def test_fifo_matches_oldest_lots_first(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)   # lot 1 @100
    _tx(conn, acc, st, "buy", "2024-06-02", 10, 140.0)   # lot 2 @140
    _tx(conn, acc, st, "sell", "2024-09-02", 12, 150.0)  # 10@100 + 2@140
    conn.commit()

    r = portfolio.realized_gains(conn, acc, 2024, "fifo")
    assert len(r["sales"]) == 1
    s = r["sales"][0]
    assert s["cost_basis"] == pytest.approx(10 * 100 + 2 * 140)
    assert s["proceeds"] == pytest.approx(12 * 150)
    assert s["gain"] == pytest.approx(1800 - 1280)
    assert r["total_gain"] == pytest.approx(520.0)


def test_lifo_matches_newest_lots_first(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    _tx(conn, acc, st, "buy", "2024-06-02", 10, 140.0)
    _tx(conn, acc, st, "sell", "2024-09-02", 12, 150.0)  # 10@140 + 2@100
    conn.commit()

    r = portfolio.realized_gains(conn, acc, 2024, "lifo")
    s = r["sales"][0]
    assert s["cost_basis"] == pytest.approx(10 * 140 + 2 * 100)
    assert s["gain"] == pytest.approx(1800 - 1600)


def test_fifo_and_lifo_differ_on_same_book(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    _tx(conn, acc, st, "buy", "2024-06-02", 10, 140.0)
    _tx(conn, acc, st, "sell", "2024-09-02", 5, 150.0)
    conn.commit()
    fifo = portfolio.realized_gains(conn, acc, 2024, "fifo")["total_gain"]
    lifo = portfolio.realized_gains(conn, acc, 2024, "lifo")["total_gain"]
    assert fifo == pytest.approx(5 * (150 - 100))   # +250
    assert lifo == pytest.approx(5 * (150 - 140))   # +50


def test_sales_filtered_by_year_and_multi_lot_split(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2023-01-02", 10, 100.0)
    _tx(conn, acc, st, "sell", "2023-12-02", 4, 110.0)   # 2023 sale: +40
    _tx(conn, acc, st, "sell", "2024-02-02", 6, 120.0)   # 2024 sale: +120
    conn.commit()

    r23 = portfolio.realized_gains(conn, acc, 2023, "fifo")
    assert [s["gain"] for s in r23["sales"]] == [pytest.approx(40.0)]
    r24 = portfolio.realized_gains(conn, acc, 2024, "fifo")
    assert r24["total_gain"] == pytest.approx(120.0)
    assert r24["sales"][0]["quantity"] == 6


def test_fees_reduce_the_gain(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    _tx(conn, acc, st, "sell", "2024-03-02", 10, 110.0, fees=5.0)
    conn.commit()
    r = portfolio.realized_gains(conn, acc, 2024, "fifo")
    # proceeds reported net of fees: 1100 - 5 = 1095; cost 1000 -> gain 95
    assert r["sales"][0]["proceeds"] == pytest.approx(1095.0)
    assert r["total_gain"] == pytest.approx(95.0)


def test_bad_method_and_missing_account_raise(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    conn.commit()
    with pytest.raises(ValueError, match="fifo"):
        portfolio.realized_gains(conn, acc, 2024, "hifo")
    with pytest.raises(ValueError, match="not found"):
        portfolio.realized_gains(conn, 999, 2024)


def test_tax_preview_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "t.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "AAPL", "quantity": 10, "price": 100.0, "currency": "EUR"})
    client.post("/api/transactions", json={
        "account_id": acc, "type": "sell", "date": "2024-07-02",
        "ticker": "AAPL", "quantity": 10, "price": 130.0, "currency": "EUR"})

    r = client.get("/api/tax/preview", params={"account_id": acc, "year": 2024})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "fifo"
    assert body["total_gain"] == pytest.approx(300.0)

    r = client.get("/api/tax/preview",
                   params={"account_id": acc, "year": 2024, "method": "hifo"})
    assert r.status_code == 400
