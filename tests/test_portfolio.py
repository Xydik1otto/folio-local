# End-to-end: seed DB -> build portfolio -> check valuation, XIRR, TWR, API.
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import backend.portfolio as portfolio_mod
from backend import fx as fxmod
from backend.db import connect, store_price, upsert_asset
from backend.main import app


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    c = connect(str(tmp_path / "test.db"))
    monkeypatch.setattr("backend.main.DB_PATH", str(tmp_path / "test.db"))
    # deterministic FX: 1 EUR = 1.10 USD, 1 EUR = 41 UAH
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10, "UAH": 41.0})
    return c


def _seed(conn):
    """Classic scenario, all in EUR for simplicity:
    dep 1000 -> buy 10 x 100 -> price up to 120 -> dep 660 -> buy 5 x 120 = 600,
    cash left 1060 -> price up to 150 -> portfolio = 1060 + 10*150 + 5*150.
    """
    cur = conn.execute(
        "INSERT INTO accounts(name, currency, cash) VALUES ('Main','EUR',0)")
    acc_id = cur.lastrowid
    st = upsert_asset(conn, "ACME", "Acme Inc", "stock", "EUR")
    rows = [
        ("deposit", "2024-01-01", None, None, 1000.0, "EUR"),
        ("buy", "2024-01-02", st, 10, 100.0, "EUR"),
        ("deposit", "2024-03-01", None, None, 660.0, "EUR"),
        ("buy", "2024-03-02", st, 5, 120.0, "EUR"),
    ]
    for typ, date, asset, qty, price, ccy in rows:
        amount = qty * price if qty else price
        conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
            " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,0,?)",
            (acc_id, asset, typ, date, qty, price, amount, ccy),
        )
    store_price(conn, "ACME", "2024-01-02", 100.0, "EUR")
    store_price(conn, "ACME", "2024-03-02", 120.0, "EUR")
    store_price(conn, "ACME", "2024-06-30", 150.0, "EUR")
    conn.commit()
    return acc_id


def test_valuation_multicurrency(conn):
    # Same scenario but the second deposit is in USD: 660 USD = 600 EUR at 1.10.
    cur = conn.execute(
        "INSERT INTO accounts(name, currency, cash) VALUES ('FxAcc','EUR',0)")
    acc = cur.lastrowid
    st = upsert_asset(conn, "MSFT", None, "stock", "USD")
    conn.executemany(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,?,?,?,?,?,0,?)",
        [
            (acc, None, "deposit", "2024-01-01", None, None, 1100.0, "USD"),
            (acc, st, "buy", "2024-01-02", 10, 100.0, 1000.0, "USD"),
            (acc, st, "sell", "2024-02-01", 2, 110.0, 220.0, "USD"),
            (acc, st, "dividend", "2024-03-01", None, None, 11.0, "USD"),
        ],
    )
    store_price(conn, "MSFT", "2024-03-01", 110.0, "USD")
    conn.commit()

    val = portfolio_mod.value_on_date(conn, acc, "2024-03-01")
    # cash: 1100 - 1000 (buy) + 220 (sell proceeds) + 11 (dividend) = 331 USD
    #       -> 331 / 1.10 = 300.909... EUR
    # cash is rounded to cents by design (display precision)
    assert val["cash"] == pytest.approx(331.0 / 1.10, abs=0.01)
    # market: 8 shares * 110 USD = 880 USD = 800 EUR
    assert val["market"] == pytest.approx(800.0, abs=1e-6)
    assert val["currency"] == "EUR"


def test_valuation_single_currency(conn):
    acc = _seed(conn)
    val = portfolio_mod.value_on_date(conn, acc, "2024-06-30")
    # cash: 1000 + 660 deposits - 1000 - 600 buys = 60
    assert val["cash"] == pytest.approx(60.0)
    assert val["market"] == pytest.approx(2250.0)   # 15 shares * 150
    assert val["total"] == pytest.approx(2310.0)


def test_xirr_matches_known_value(conn):
    acc = _seed(conn)
    x = portfolio_mod.portfolio_xirr(conn, acc, "2024-06-30")
    # flows: -1000 (Jan 1), -660 (Mar 1), +2310 (Jun 30) -> ~ +125% annualised
    assert x is not None
    assert 0.5 < x < 2.0
    # and NPV at that rate must vanish
    from backend.math_finance import npv
    flows = portfolio_mod.external_flows(conn, acc)
    flows.append((dt.date(2024, 6, 30), 2310.0))
    assert npv(flows, x) == pytest.approx(0.0, abs=1e-6)


def test_twr_chain_of_two_periods(conn):
    acc = _seed(conn)
    t = portfolio_mod.twr_series(conn, acc, "2024-01-01", "2024-06-30")
    # Period 1: value 1000 (cash 0 + 10 shares @100) -> +660 deposit at Mar 1,
    # value after flow = 1660; performance = (1660-660)/1000 = 1.0 (+0%, price flat).
    # Period 2: cash 1060? no - cash 60 + 15 shares @150 = 2310; 2310/1660.
    assert t is not None
    assert t == pytest.approx((1.0 * (2310.0 / 1660.0)) - 1.0, rel=1e-9)


# --- API layer ---------------------------------------------------------------

def test_api_full_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "api.db"))
    client = TestClient(app)

    r = client.get("/api/health")
    assert r.status_code == 200

    r = client.post("/api/accounts", json={"name": "Main", "currency": "EUR"})
    assert r.status_code == 200
    acc = r.json()["id"]

    r = client.post("/api/fx", json={"date": "2024-01-01", "rates": {"USD": 1.10}})
    assert r.status_code == 200

    r = client.post("/api/transactions", json={
        "account_id": acc, "type": "deposit", "date": "2024-01-01",
        "amount": 1000.0, "currency": "EUR"})
    assert r.status_code == 200

    r = client.post("/api/transactions", json={
        "account_id": acc, "type": "buy", "date": "2024-01-02",
        "ticker": "AAPL", "quantity": 5, "price": 100.0, "currency": "EUR"})
    assert r.status_code == 200

    r = client.post("/api/prices", params={
        "ticker": "AAPL", "date": "2024-06-30", "price": 120.0, "currency": "EUR"})
    assert r.status_code == 200

    r = client.get("/api/portfolio", params={"account_id": acc, "as_of": "2024-06-30"})
    assert r.status_code == 200
    body = r.json()
    assert body["cash"] == pytest.approx(500.0)
    assert body["market"] == pytest.approx(600.0)
    assert body["total"] == pytest.approx(1100.0)
    assert body["pnl"] == pytest.approx(100.0)
    assert body["xirr"] is not None and body["xirr"] > 0

    r = client.get("/api/portfolio/twr",
                   params={"account_id": acc, "start": "2024-01-01", "end": "2024-06-30"})
    assert r.status_code == 200
    # TWR of the WHOLE portfolio: +100 on 1000 with no intermediate flows
    # (the deposit happened on the start date = opening capital).
    assert r.json()["twr"] == pytest.approx(0.10, abs=1e-6)

    r = client.get("/api/portfolio/history",
                   params={"account_id": acc, "start": "2024-01-01", "end": "2024-06-30"})
    assert r.status_code == 200
    assert len(r.json()["points"]) >= 2


def test_api_csv_import(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "csv.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T", "currency": "EUR"}).json()["id"]
    csv_text = (
        "date,ticker,action,quantity,price,currency,fees,name,kind\n"
        "2024-01-01,,deposit,,1000,EUR,,,\n"
        "2024-01-02,AAPL,buy,10,190,USD,1.2,Apple Inc,stock\n"
        "2024-03-01,AAPL,dividend,,24,USD,,,stock\n"
    )
    r = client.post("/api/import/csv", json={"account_id": acc, "csv_text": csv_text})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 3

    txs = client.get("/api/transactions", params={"account_id": acc}).json()
    assert len(txs) == 3
    buy = [t for t in txs if t["type"] == "buy"][0]
    assert buy["quantity"] == 10 and buy["price"] == 190.0
    assert buy["asset_currency"] == "USD"
    assets = client.get("/api/assets").json()
    assert any(a["ticker"] == "AAPL" and a["kind"] == "stock" for a in assets)


def test_csv_import_validation(conn):
    from backend.csv_import import ImportRowError, parse_csv

    good = parse_csv(
        "date,ticker,action,quantity,price,currency\n"
        "2024-01-01,,deposit,,1000,EUR\n"
        "2024-01-02,AAPL,buy,5,190.5,USD\n"
    )
    assert good[1]["amount"] == pytest.approx(5 * 190.5)
    assert good[1]["currency"] == "USD"

    with pytest.raises(ImportRowError):
        parse_csv("date,ticker,action\n2024-01-01,X,buy")  # missing columns
    with pytest.raises(ImportRowError):
        parse_csv(
            "date,ticker,action,quantity,price,currency\n"
            "2024-01-01,X,purchase,1,1,EUR\n")  # bad action
    with pytest.raises(ImportRowError):
        parse_csv(
            "date,ticker,action,quantity,price,currency\n"
            "01/02/2024,X,buy,1,1,EUR\n")  # bad date format
