# Benchmark comparison: portfolio value vs SPY (Stooq), normalized to 100.
import pytest
from fastapi.testclient import TestClient

from backend import prices
from backend.db import connect, store_price, upsert_asset


@pytest.fixture()
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "bench.db"))
    from backend.main import app
    client = TestClient(app)
    conn = connect(str(tmp_path / "bench.db"))
    from backend import fx as fxmod
    fxmod.store_rates(conn, "2024-01-01", {"EUR": 1.0})
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    st = upsert_asset(conn, "ACME", None, "stock", "EUR")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'deposit','2024-01-01',"
        "NULL,NULL,1000,0,'EUR')", (acc, st))
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',10,100,"
        "1000,0,'EUR')", (acc, st))
    store_price(conn, "ACME", "2024-01-01", 100.0, "EUR")
    store_price(conn, "ACME", "2024-03-01", 120.0, "EUR")
    conn.commit()

    fake_bench = [("2024-01-01", 400.0), ("2024-02-01", 440.0),
                  ("2024-03-01", 480.0)]
    seen = {}

    def fake_stooq(symbol, start=None, end=None):
        seen["symbol"] = symbol
        return list(fake_bench)

    monkeypatch.setattr(prices, "fetch_stooq_history", fake_stooq)
    return client, acc, seen


def test_benchmark_normalized_to_100(api):
    client, acc, _ = api
    r = client.get(f"/api/portfolio/benchmark?account_id={acc}"
                   "&start=2024-01-01&end=2024-03-01")
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "SPY.US"
    pts = body["points"]
    assert pts[0]["portfolio"] == 100.0 and pts[0]["benchmark"] == 100.0
    last = pts[-1]
    # portfolio: 1000 -> 1200 (+20%); benchmark: 400 -> 480 (+20%)
    assert last["portfolio"] == pytest.approx(120.0)
    assert last["benchmark"] == pytest.approx(120.0)


def test_benchmark_default_symbol_gets_us_suffix(api):
    client, acc, seen = api
    client.get(f"/api/portfolio/benchmark?account_id={acc}"
               "&start=2024-01-01&end=2024-03-01")
    assert seen["symbol"] == "spy.us"


def test_benchmark_explicit_symbol_kept_as_is(api):
    client, acc, seen = api
    client.get(f"/api/portfolio/benchmark?account_id={acc}"
               "&start=2024-01-01&end=2024-03-01&symbol=QQQ.US")
    assert seen["symbol"] == "QQQ.US"


def test_benchmark_mid_series_dates_filled(api):
    client, acc, _ = api
    body = client.get(f"/api/portfolio/benchmark?account_id={acc}"
                      "&start=2024-01-01&end=2024-03-01").json()
    # every event date carries a benchmark value (last close <= date)
    jan2 = [p for p in body["points"] if p["date"] == "2024-01-02"]
    assert jan2 and jan2[0]["benchmark"] == pytest.approx(100.0)
    assert len(body["points"]) >= 3


def test_benchmark_fetch_failure_is_502(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "e.db"))
    from backend.main import app
    client = TestClient(app)
    conn = connect(str(tmp_path / "e.db"))
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    conn.commit()

    def boom(symbol, start=None, end=None):
        raise OSError("network down")

    monkeypatch.setattr(prices, "fetch_stooq_history", boom)
    r = client.get(f"/api/portfolio/benchmark?account_id={acc}"
                   "&start=2024-01-01&end=2024-03-01")
    assert r.status_code == 502


def test_benchmark_unknown_symbol_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "u.db"))
    from backend.main import app
    client = TestClient(app)
    conn = connect(str(tmp_path / "u.db"))
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('M', 'EUR')").lastrowid
    conn.commit()
    monkeypatch.setattr(prices, "fetch_stooq_history", lambda *a, **k: [])
    r = client.get(f"/api/portfolio/benchmark?account_id={acc}"
                   "&start=2024-01-01&end=2024-03-01")
    assert r.status_code == 404
