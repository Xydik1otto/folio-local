# Crypto pricing via the free CoinGecko history endpoint + unification with
# stocks in holdings/allocation (everything goes through price snapshots).
import json
import urllib.request

import pytest
from fastapi.testclient import TestClient

from backend import portfolio, prices
from backend.db import connect, latest_price, store_price, upsert_asset


@pytest.fixture()
def conn():
    c = connect(":memory:")
    from backend import fx as fxmod
    fxmod.store_rates(c, "2024-01-01", {"EUR": 1.0, "USD": 1.10})
    return c


class _Resp:
    def __init__(self, payload):
        self._bytes = json.dumps(payload).encode()

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_known_coins_map_btc_eth_sol():
    assert prices.KNOWN_COINS["BTC"] == "bitcoin"
    assert prices.KNOWN_COINS["ETH"] == "ethereum"
    assert prices.KNOWN_COINS["SOL"] == "solana"


def test_fetch_coingecko_history_parses_price(monkeypatch):
    payload = {"market_data": {"current_price": {"usd": 61234.5}}}
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        return _Resp(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    out = prices.fetch_coingecko_history("bitcoin", "2024-06-01")
    assert out == ("2024-06-01", 61234.5)
    # date must be sent in CoinGecko's DD-MM-YYYY format
    assert "date=01-06-2024" in seen["url"]
    assert "coins/bitcoin/history" in seen["url"]


def test_fetch_coingecko_history_garbage_returns_none(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=None: _Resp({"no_such_key": 1}))
    assert prices.fetch_coingecko_history("bitcoin", "2024-06-01") is None


def test_backfill_crypto_stores_history(conn, monkeypatch):
    upsert_asset(conn, "BTC", "bitcoin", "crypto", "USD")
    seq = {"2024-01-01": 40000.0, "2024-01-02": 41000.0, "2024-01-03": 42000.0}
    calls = []

    def fake_hist(coin_id, date):
        calls.append((coin_id, date))
        return (date, seq[date]) if date in seq else None

    monkeypatch.setattr(prices, "fetch_coingecko_history", fake_hist)
    r = prices.backfill_prices(conn, "btc", "2024-01-01", "2024-01-04")
    assert r["stored"] == 3
    assert r["ticker"] == "BTC"
    assert all(c[0] == "bitcoin" for c in calls)
    snap = latest_price(conn, "BTC", "2024-01-03")
    assert snap["price"] == pytest.approx(42000.0)
    assert snap["currency"] == "USD"


def test_backfill_crypto_without_asset_row_uses_known_map(conn, monkeypatch):
    # no asset row at all: BTC is still recognised as crypto via KNOWN_COINS
    monkeypatch.setattr(prices, "fetch_coingecko_history",
                        lambda coin, date: (date, 100.0) if date == "2024-01-02" else None)
    r = prices.backfill_prices(conn, "BTC", "2024-01-01", "2024-01-03")
    assert r["stored"] == 1
    assert latest_price(conn, "BTC", "2024-01-03")["price"] == 100.0


def test_backfill_unknown_ticker_stays_on_stooq(conn, monkeypatch):
    # unknown ticker (not crypto) must still try Stooq, not CoinGecko
    called = {}

    def fake_stooq(symbol, start, end):
        called["symbol"] = symbol
        return []

    monkeypatch.setattr(prices, "fetch_stooq_history", fake_stooq)
    r = prices.backfill_prices(conn, "ACME", "2024-01-01", "2024-01-02")
    assert called["symbol"] == "acme" and r["stored"] == 0


def test_backfill_unknown_coin_reports_error(conn):
    r = prices.backfill_crypto(conn, "FOOCOIN", "2024-01-01", "2024-01-02")
    assert r["stored"] == 0
    assert "coin id" in r["error"]


def test_holdings_unified_with_crypto_prices(conn):
    # BTC buy priced in USD; holdings/allocation must treat it like any stock
    acc = conn.execute(
        "INSERT INTO accounts(name, currency) VALUES ('C', 'EUR')").lastrowid
    btc = upsert_asset(conn, "BTC", "bitcoin", "crypto", "USD")
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'deposit','2024-01-01',"
        "NULL, NULL, 20000, 0, 'EUR')", (acc, btc))
    conn.execute(
        "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
        " price, amount, fees, currency) VALUES (?,?,'buy','2024-01-02',0.5,40000,"
        "20000,0,'USD')", (acc, btc))
    store_price(conn, "BTC", "2024-01-03", 44000.0, "USD")
    conn.commit()

    h = portfolio.holdings(conn, acc, as_of="2024-03-01")
    row = h["holdings"][0]
    assert row["ticker"] == "BTC"
    assert row["current_value"] == pytest.approx(0.5 * 44000 / 1.10)  # 20000 EUR
    assert row["pnl"] == pytest.approx(round(20000.0 - 0.5 * 40000 / 1.10, 2))

    alloc = portfolio.allocation(conn, acc, as_of="2024-03-01")
    assert alloc["groups"]["crypto"] == pytest.approx(20000.0)
    assert alloc["shares"]["crypto"] == pytest.approx(0.916667)


def test_api_backfill_endpoint_routes_crypto(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "crypto.db"))
    monkeypatch.setattr(prices, "fetch_coingecko_history",
                        lambda coin, date: (date, 2500.0))
    from backend.main import app
    c = TestClient(app)
    acc = c.post("/api/accounts", json={"name": "C", "currency": "EUR"}).json()
    r = c.post("/api/prices/backfill", json={
        "ticker": "ETH", "start": "2024-01-01", "end": "2024-01-02"})
    assert r.status_code == 200
    body = r.json()
    assert body["stored"] == 2 and body["ticker"] == "ETH"


def test_api_add_transaction_auto_detects_crypto(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "auto.db"))
    from backend.main import app
    c = TestClient(app)
    acc = c.post("/api/accounts", json={"name": "C", "currency": "EUR"}).json()
    r = c.post("/api/transactions", json={
        "account_id": acc["id"], "type": "buy", "date": "2024-01-02",
        "ticker": "SOL", "quantity": 10, "price": 100, "currency": "USD"})
    assert r.status_code == 200
    assets = c.get("/api/assets").json()
    sol = [a for a in assets if a["ticker"] == "SOL"][0]
    assert sol["kind"] == "crypto" and sol["name"] == "solana"
