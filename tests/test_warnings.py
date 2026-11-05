# Warnings panel: missing prices, missing FX rates, stale quotes.
import pytest
from fastapi.testclient import TestClient

from backend import warnings as warnings_mod
from backend.db import connect, store_price, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


def _acc(conn, ccy="EUR"):
    return conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', ?)", (ccy,)).lastrowid


def _tx(conn, acc, asset, typ, date, qty=None, price=None, ccy="EUR"):
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,?,?)",
        (acc, asset, typ, date, qty, price, None, 0, ccy))


def test_missing_price_on_buy(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, None)
    conn.commit()
    w = warnings_mod.collect_warnings(conn, acc, as_of="2024-03-01")
    kinds = [x["type"] for x in w["warnings"]]
    assert "missing_price" in kinds
    item = [x for x in w["warnings"] if x["type"] == "missing_price"][0]
    assert item["severity"] == "error" and item["ticker"] == "ACME"


def test_missing_fx_rate(conn):
    acc = _acc(conn, ccy="EUR")
    st = upsert_asset(conn, "ACME", None, "stock", "USD")
    # transaction in USD, but no USD rate stored on/after its date is missing
    conn.execute("DELETE FROM fx_rates WHERE currency = 'USD'")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0, ccy="USD")
    conn.commit()
    w = warnings_mod.collect_warnings(conn, acc, as_of="2024-03-01")
    fx = [x for x in w["warnings"] if x["type"] == "missing_fx"]
    assert fx and fx[0]["currency"] == "USD" and fx[0]["severity"] == "error"


def test_no_price_data_for_held_ticker(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    conn.commit()
    w = warnings_mod.collect_warnings(conn, acc, as_of="2024-03-01")
    kinds = [x["type"] for x in w["warnings"]]
    assert "no_price_data" in kinds


def test_stale_price_warning(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    store_price(conn, "ACME", "2024-01-03", 110.0, "EUR")
    conn.commit()
    w = warnings_mod.collect_warnings(conn, acc, as_of="2024-03-15")
    stale = [x for x in w["warnings"] if x["type"] == "stale_price"]
    assert stale and stale[0]["age_days"] > 30
    assert stale[0]["severity"] == "warning"


def test_fresh_quotes_no_warnings(conn):
    acc = _acc(conn)
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    _tx(conn, acc, st, "buy", "2024-01-02", 10, 100.0)
    store_price(conn, "ACME", "2024-02-20", 110.0, "EUR")
    conn.commit()
    w = warnings_mod.collect_warnings(conn, acc, as_of="2024-03-01")
    assert w["count"] == 0 and w["warnings"] == []


def test_unknown_account_raises(conn):
    with pytest.raises(ValueError):
        warnings_mod.collect_warnings(conn, 999)


def test_warnings_api(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "w.db"))
    from backend.main import app
    client = TestClient(app)
    acc = client.post("/api/accounts",
                      json={"name": "M", "currency": "EUR"}).json()["id"]
    # buy without a price -> warning
    r = client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "ACME", "quantity": 10, "currency": "EUR"})
    assert r.status_code == 200
    r = client.get(f"/api/warnings?account_id={acc}&as_of=2024-03-01")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any(x["type"] == "missing_price" for x in body["warnings"])

    r = client.get("/api/warnings?account_id=999")
    assert r.status_code == 400
