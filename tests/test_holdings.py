# Holdings per account: quantity, average price, current value, P/L.
import pytest

from backend import portfolio
from backend.db import connect, store_price, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    # deterministic FX: 1 EUR = 1.10 USD
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


def _acc(conn, name="Main", ccy="EUR"):
    return conn.execute(
        "INSERT INTO accounts(name, currency, cash) VALUES (?, ?, 0)",
        (name, ccy)).lastrowid


def test_holdings_basic_avg_price_and_pnl(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    # buy 10 @ 100, then 10 @ 140 -> avg 120, qty 20
    for date, qty, px in (("2024-01-02", 10, 100.0), ("2024-02-02", 10, 140.0)):
        conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
            " price, amount, fees, currency) VALUES (?,?,'buy',?,?,?,?,0,?)",
            (acc, st, date, qty, px, qty * px, "EUR"))
    store_price(conn, "ACME", "2024-03-01", 150.0, "EUR")
    conn.commit()

    h = portfolio.holdings(conn, acc, as_of="2024-03-01")
    row = h["holdings"][0]
    assert row["ticker"] == "ACME"
    assert row["quantity"] == 20
    assert row["avg_price"] == pytest.approx(120.0)
    assert row["current_value"] == pytest.approx(3000.0)   # 20 * 150
    assert row["cost_basis"] == pytest.approx(2400.0)      # 10*100 + 10*140
    assert row["pnl"] == pytest.approx(600.0)
    assert row["pnl_pct"] == pytest.approx(0.25)


def test_holdings_sell_reduces_cost_proportionally(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',10,100,1000,0,'EUR')",
        (acc, st))
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'sell','2024-02-01',4,110,440,0,'EUR')",
        (acc, st))
    store_price(conn, "ACME", "2024-03-01", 120.0, "EUR")
    conn.commit()

    row = portfolio.holdings(conn, acc, as_of="2024-03-01")["holdings"][0]
    assert row["quantity"] == 6
    assert row["avg_price"] == pytest.approx(100.0)        # avg cost unchanged
    assert row["cost_basis"] == pytest.approx(600.0)       # 1000 * 6/10
    assert row["current_value"] == pytest.approx(720.0)
    assert row["pnl"] == pytest.approx(120.0)


def test_holdings_full_exit_drops_ticker(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',5,100,500,0,'EUR')",
        (acc, st))
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'sell','2024-02-01',5,110,550,0,'EUR')",
        (acc, st))
    store_price(conn, "ACME", "2024-03-01", 120.0, "EUR")
    conn.commit()
    assert portfolio.holdings(conn, acc, as_of="2024-03-01")["holdings"] == []


def test_holdings_fx_conversion(conn):
    # USD buys in an EUR account: cost converted at transaction-date rate.
    acc = _acc(conn, "Fx", "EUR")
    st = upsert_asset(conn, "AAPL", None, "stock", "USD")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',10,110,1100,0,'USD')",
        (acc, st))
    store_price(conn, "AAPL", "2024-03-01", 110.0, "USD")
    conn.commit()

    row = portfolio.holdings(conn, acc, as_of="2024-03-01")["holdings"][0]
    # cost: 1100 USD / 1.10 = 1000 EUR; value: 10 * 110 USD / 1.10 = 1000 EUR
    assert row["cost_basis"] == pytest.approx(1000.0)
    assert row["current_value"] == pytest.approx(1000.0)
    assert row["pnl"] == pytest.approx(0.0)


def test_holdings_missing_price_raises(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ORPH", None, "stock", "EUR")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',1,10,10,0,'EUR')",
        (acc, st))
    conn.commit()
    with pytest.raises(ValueError, match="ORPH"):
        portfolio.holdings(conn, acc, as_of="2024-03-01")


def test_holdings_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "h.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "AAPL", "quantity": 5, "price": 100.0, "currency": "EUR"})
    client.post("/api/prices", params={
        "ticker": "AAPL", "date": "2024-06-30", "price": 120.0, "currency": "EUR"})
    r = client.get("/api/holdings", params={"account_id": acc, "as_of": "2024-06-30"})
    assert r.status_code == 200
    row = r.json()["holdings"][0]
    assert row["quantity"] == 5
    assert row["avg_price"] == pytest.approx(100.0)
    assert row["current_value"] == pytest.approx(600.0)
    assert row["pnl"] == pytest.approx(100.0)
