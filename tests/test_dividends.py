# Dividend calendar: monthly/per-ticker dividend summary in account currency.
import pytest

from backend import portfolio
from backend.db import connect, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


def _div(conn, acc, asset, date, amount, ccy):
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'dividend',?,NULL,NULL,?,0,?)",
        (acc, asset, date, amount, ccy))


def test_dividend_summary_monthly_and_per_ticker(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    aapl = upsert_asset(conn, "AAPL", None, "stock", "USD")
    msft = upsert_asset(conn, "MSFT", None, "stock", "USD")
    _div(conn, acc, aapl, "2024-02-05", 11.0, "USD")   # 10 EUR
    _div(conn, acc, aapl, "2024-05-10", 22.0, "USD")   # 20 EUR
    _div(conn, acc, msft, "2024-05-12", 10.0, "EUR")
    conn.commit()

    s = portfolio.dividend_summary(conn, acc)
    assert s["currency"] == "EUR"
    assert s["year_total"] == pytest.approx(40.0)  # 10 + 20 + 10 EUR
    assert [m["month"] for m in s["months"]] == ["2024-02", "2024-05"]
    may = s["months"][1]
    assert may["total"] == pytest.approx(30.0)
    assert may["tickers"] == {"AAPL": 20.0, "MSFT": 10.0}
    assert s["by_ticker"]["AAPL"] == pytest.approx(30.0)
    assert s["years"] == ["2024"]


def test_dividend_summary_year_filter(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    aapl = upsert_asset(conn, "AAPL", None, "stock", "USD")
    _div(conn, acc, aapl, "2023-11-05", 5.0, "EUR")
    _div(conn, acc, aapl, "2024-01-05", 7.0, "EUR")
    conn.commit()

    s2024 = portfolio.dividend_summary(conn, acc, year=2024)
    assert s2024["year_total"] == pytest.approx(7.0)
    assert [m["month"] for m in s2024["months"]] == ["2024-01"]
    assert s2024["years"] == ["2024", "2023"]


def test_dividend_summary_empty(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    conn.commit()
    s = portfolio.dividend_summary(conn, acc)
    assert s["months"] == [] and s["year_total"] == 0.0


def test_dividends_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "d.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T"}).json()["id"]
    client.post("/api/transactions", json={
        "account_id": acc, "type": "dividend", "date": "2024-03-01",
        "ticker": "AAPL", "amount": 24.0, "currency": "EUR"})
    r = client.get("/api/dividends", params={"account_id": acc})
    assert r.status_code == 200
    body = r.json()
    assert body["year_total"] == pytest.approx(24.0)
    assert body["months"][0]["tickers"]["AAPL"] == pytest.approx(24.0)

    r = client.get("/api/dividends", params={"account_id": 999})
    assert r.status_code == 400
