# First-run demo data: opt-in «Load demo data» button (POST /api/demo-data).
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


def test_demo_endpoint_creates_account_and_transactions(dbfile):
    r = client.post("/api/demo-data")
    assert r.status_code == 200
    body = r.json()
    assert body["account"] == "Demo"
    assert body["created"] >= 8

    c = connect(dbfile)
    acc = c.execute("SELECT id, currency FROM accounts WHERE name='Demo'").fetchone()
    assert acc["currency"] == "EUR"
    rows = c.execute(
        "SELECT t.type, a.ticker, a.kind FROM transactions t "
        "LEFT JOIN assets a ON a.id = t.asset_id WHERE t.account_id = ?",
        (acc["id"],)).fetchall()
    c.close()
    types = [r["type"] for r in rows]
    assert types.count("buy") >= 4 and "sell" in types and "dividend" in types
    kinds = {r["kind"] for r in rows if r["kind"]}
    assert {"stock", "etf", "crypto"} <= kinds


def test_demo_endpoint_is_idempotent(dbfile):
    assert client.post("/api/demo-data").status_code == 200
    r = client.post("/api/demo-data")
    assert r.status_code == 409
    # still exactly one Demo account
    c = connect(dbfile)
    n = c.execute("SELECT COUNT(*) FROM accounts WHERE name='Demo'").fetchone()[0]
    c.close()
    assert n == 1


def test_demo_does_not_touch_other_accounts(dbfile):
    c = connect(dbfile)
    with c:
        c.execute("INSERT INTO accounts(name, currency) VALUES ('Mine','EUR')")
    c.close()
    client.post("/api/demo-data")
    c = connect(dbfile)
    n = c.execute("SELECT COUNT(*) FROM transactions t JOIN accounts a "
                  "ON a.id = t.account_id WHERE a.name='Mine'").fetchone()[0]
    c.close()
    assert n == 0


def test_demo_button_in_ui():
    html = client.get("/").text
    assert "loadDemo()" in html and "/api/demo-data" in html


def test_demo_rows_have_valid_dates(dbfile):
    import re
    client.post("/api/demo-data")
    c = connect(dbfile)
    dates = [r[0] for r in c.execute("SELECT date FROM transactions")]
    c.close()
    for d in dates:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
