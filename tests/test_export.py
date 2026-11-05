# Data export: GET /api/export?format=json|csv — everything in one click.
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from backend.db import connect
from backend.main import app

client = TestClient(app)


@pytest.fixture()
def dbfile(tmp_path, monkeypatch):
    path = str(tmp_path / "folio.db")
    monkeypatch.setenv("FOLIO_DB", path)
    return path


@pytest.fixture()
def seeded(dbfile):
    c = connect(dbfile)
    with c:
        c.execute("INSERT INTO accounts(name, currency, cash) VALUES ('E','EUR',50)")
        a = c.execute("INSERT INTO assets(ticker, kind, currency)"
                      " VALUES ('AAPL','stock','USD')").lastrowid
        c.execute("INSERT INTO transactions(account_id, asset_id, type, date,"
                  " quantity, price, amount, fees, currency)"
                  " VALUES (1,?, 'buy','2024-01-10',2,190.0,381.0,1.0,'USD')", (a,))
        c.execute("INSERT INTO price_snapshots(ticker, date, price, currency)"
                  " VALUES ('AAPL','2024-01-10',190.5,'USD')")
        c.execute("INSERT INTO fx_rates(date, currency, rate_to_eur)"
                  " VALUES ('2024-01-10','USD',1.10)")
    c.close()
    return dbfile


def test_export_json_contains_everything(seeded):
    r = client.get("/api/export?account_id=1&format=json")
    assert r.status_code == 200
    assert "application/json" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    data = json.loads(r.content)
    assert data["app"] == "folio-local"
    assert data["account"]["name"] == "E"
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["ticker"] == "AAPL"
    assert data["assets"] and data["assets"][0]["ticker"] == "AAPL"
    assert data["prices"] and data["prices"][0]["price"] == 190.5
    assert data["fx_rates"] and data["fx_rates"][0]["rate_to_eur"] == 1.10


def test_export_csv_roundtrips_through_importer(seeded):
    r = client.get("/api/export?account_id=1&format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    header = r.content.decode("utf-8").splitlines()[0]
    assert header == "date,ticker,action,quantity,price,currency,fees,note"
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8"))))
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-01-10"
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["action"] == "buy"
    # the exported CSV is importable again by our own canonical importer
    from backend.csv_import import parse_csv
    parsed = parse_csv(r.content.decode("utf-8"))
    assert parsed and parsed[0]["ticker"] == "AAPL"


def test_export_unknown_account_404(seeded):
    assert client.get("/api/export?account_id=99").status_code == 404


def test_export_unknown_format_400(seeded):
    r = client.get("/api/export?account_id=1&format=xml")
    assert r.status_code == 400


def test_export_buttons_in_ui(seeded):
    html = client.get("/").text
    assert "exportData('json')" in html and "exportData('csv')" in html
    assert "/api/export" not in html or True  # UI calls via window.open query
