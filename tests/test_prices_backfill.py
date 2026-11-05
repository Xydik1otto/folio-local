# Price history backfill over a date range (Stooq), with a mocked HTTP layer.
import io
import urllib.request

import pytest

from backend import prices
from backend.db import connect, latest_price


STOOQ_CSV = (
    "Date,Open,High,Low,Close,Volume\n"
    "2024-01-02,185.0,187.0,184.0,186.5,51000000\n"
    "2024-01-03,186.5,188.0,186.0,187.9,48000000\n"
    "2024-01-04,187.9,190.0,187.0,189.4,52000000\n"
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def conn():
    return connect(":memory:")


def test_fetch_stooq_history_parses_range(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=30):
        seen["url"] = req.full_url
        return FakeResponse(STOOQ_CSV.encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    quotes = prices.fetch_stooq_history("aapl.us", "2024-01-02", "2024-01-04")
    assert "d1=20240102" in seen["url"] and "d2=20240104" in seen["url"]
    assert quotes == [("2024-01-02", 186.5), ("2024-01-03", 187.9),
                      ("2024-01-04", 189.4)]


def test_fetch_stooq_history_network_error_raises(monkeypatch):
    def boom(req, timeout=30):
        raise OSError("no network")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(OSError):
        prices.fetch_stooq_history("aapl.us")


def test_backfill_stores_snapshots(conn, monkeypatch):
    monkeypatch.setattr(prices, "fetch_stooq_history",
                        lambda s, a, b: [("2024-01-02", 186.5), ("2024-01-03", 187.9)])
    res = prices.backfill_prices(conn, "AAPL", "2024-01-02", "2024-01-03")
    assert res == {"ticker": "AAPL", "start": "2024-01-02",
                   "end": "2024-01-03", "stored": 2}
    assert latest_price(conn, "AAPL")["price"] == pytest.approx(187.9)
    assert latest_price(conn, "AAPL", "2024-01-02")["price"] == pytest.approx(186.5)


def test_backfill_reports_fetch_failure(conn, monkeypatch):
    def boom(s, a, b):
        raise OSError("timeout")

    monkeypatch.setattr(prices, "fetch_stooq_history", boom)
    res = prices.backfill_prices(conn, "AAPL", "2024-01-02", "2024-01-03")
    assert res["stored"] == 0 and "fetch failed" in res["error"]


def test_backfill_rejects_bad_dates(conn):
    with pytest.raises(ValueError):
        prices.backfill_prices(conn, "AAPL", "not-a-date", "2024-01-03")


def test_backfill_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "bf.db"))
    monkeypatch.setattr(prices, "fetch_stooq_history",
                        lambda s, a, b: [("2024-01-02", 100.0)])
    client = TestClient(app)
    r = client.post("/api/prices/backfill",
                    json={"ticker": "msft", "start": "2024-01-02", "end": "2024-01-02"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stored"] == 1 and body["ticker"] == "MSFT"

    r = client.post("/api/prices/backfill",
                    json={"ticker": "MSFT", "start": "bad", "end": "2024-01-02"})
    assert r.status_code == 400
