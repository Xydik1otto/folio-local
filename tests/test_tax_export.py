# Tax report export: CSV file + printable HTML, FIFO/LIFO, per year.
import pytest
from fastapi.testclient import TestClient

from backend import report as report_mod
from backend.db import connect, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


@pytest.fixture()
def populated(conn):
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    for typ, date, qty, price in (
            ("buy", "2024-01-02", 10, 100.0),
            ("buy", "2024-06-02", 10, 140.0),
            ("sell", "2024-09-02", 12, 150.0)):
        conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date,"
            " quantity, price, amount, fees, currency) VALUES (?,?,?,?,?,"
            "?,NULL,0,'EUR')", (acc, st, typ, date, qty, price))
    conn.commit()
    return acc


def _report():
    return {"method": "fifo", "year": 2024, "currency": "EUR",
            "sales": [{"date": "2024-09-02", "ticker": "ACME",
                       "quantity": 12.0, "proceeds": 1800.0,
                       "cost_basis": 1280.0, "gain": 520.0}],
            "total_gain": 520.0}


def test_tax_csv_rows_and_total():
    csv_text = report_mod.tax_csv(_report())
    lines = csv_text.strip().splitlines()
    assert lines[0] == "date,ticker,quantity,proceeds,cost_basis,gain,currency"
    assert lines[1] == "2024-09-02,ACME,12.0,1800.0,1280.0,520.0,EUR"
    assert lines[2] == ",TOTAL FIFO 2024,,,,520.0,EUR"


def test_tax_csv_quotes_commas():
    r = _report()
    r["sales"][0]["ticker"] = "BRK,B"
    csv_text = report_mod.tax_csv(r)
    assert '"BRK,B"' in csv_text


def test_tax_csv_empty_year():
    r = _report()
    r["sales"] = []
    r["total_gain"] = 0.0
    lines = report_mod.tax_csv(r).strip().splitlines()
    assert len(lines) == 2  # header + total


def test_tax_html_printable_document():
    html = report_mod.tax_html(_report())
    assert html.startswith("<!DOCTYPE html>")
    assert 'lang="uk"' in html
    assert "Податковий звіт — реалізовані прибутки 2024" in html
    assert "ACME" in html and "520.00" in html
    assert "@media print" in html  # print stylesheet
    assert "TOTAL" in html or "Разом" in html


def test_tax_api_csv_export(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "tax.db"))
    conn = connect(str(tmp_path / "tax.db"))
    from backend import fx as fxmod
    fxmod.store_rates(conn, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    for typ, date, qty, price in (
            ("buy", "2024-01-02", 10, 100.0),
            ("buy", "2024-06-02", 10, 140.0),
            ("sell", "2024-09-02", 12, 150.0)):
        conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date,"
            " quantity, price, amount, fees, currency) VALUES (?,?,?,?,?,"
            "?,NULL,0,'EUR')", (acc, st, typ, date, qty, price))
    conn.commit()

    from backend.main import app
    client = TestClient(app)
    r = client.get(f"/api/tax/export?account_id={acc}&year=2024&method=fifo&format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    body = r.text.strip().splitlines()
    assert body[0].startswith("date,ticker")
    assert "2024-09-02,ACME" in body[1]
    assert body[-1].endswith("520.0,EUR")

    r = client.get(f"/api/tax/export?account_id={acc}&year=2024&format=html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Податковий звіт" in r.text

    r = client.get(f"/api/tax/export?account_id={acc}&year=2024&format=xml")
    assert r.status_code == 400

    r = client.get("/api/tax/export?account_id=999&year=2024")
    assert r.status_code == 400
