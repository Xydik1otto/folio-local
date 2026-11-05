# Crypto explorer import: pure rawaddr parser + offline network tests + API.
import io
import json
import urllib.request

import pytest
from fastapi.testclient import TestClient

from backend import crypto_explorer as ce
from backend.main import app

ADDRESS = "1A1zP1eP5QGefi2qHNfRjvG4v1k8p7jT8X"  # base58-shaped test address

# Minimal blockchain.info /rawaddr shape (satoshis, epoch seconds, hash).
PAYLOAD = {
    "address": ADDRESS,
    "txs": [
        # incoming 0.5 BTC
        {"hash": "aa11" * 8, "time": 1700000000, "result": 50_000_000},
        # self-transfer: net 0 -> skipped
        {"hash": "bb22" * 8, "time": 1700100000, "result": 0},
        # outgoing: -1.002 BTC net = 1.0 sent + 0.002 miner fee
        {"hash": "cc33" * 8, "time": 1700200000, "result": -100_200_000,
         "fee": 200_000},
    ],
}


def test_parse_incoming_becomes_buy_outgoing_becomes_sell_plus_fee():
    txs = ce.transactions_from_payload(PAYLOAD, ADDRESS)
    assert [t["type"] for t in txs] == ["buy", "sell", "fee"]  # oldest first
    buy, sell, fee = txs
    assert buy["date"] == "2023-11-14" and buy["quantity"] == 0.5
    assert buy["price"] is None and buy["currency"] == "BTC"
    assert sell["quantity"] == 1.0          # net sent, change/fee excluded
    assert fee["amount"] == 0.002
    for t in txs:
        assert t["ticker"] == "BTC"


def test_parse_skips_nothing_on_empty_address_history():
    assert ce.transactions_from_payload({"txs": []}, ADDRESS) == []


def test_parse_rejects_bad_payloads():
    with pytest.raises(ce.ExplorerError):
        ce.transactions_from_payload({}, ADDRESS)
    with pytest.raises(ce.ExplorerError):
        ce.transactions_from_payload({"txs": ["nope"]}, ADDRESS)
    with pytest.raises(ce.ExplorerError):
        ce.transactions_from_payload({"txs": [{"time": 1}]}, ADDRESS)  # no result
    with pytest.raises(ce.ExplorerError):
        ce.transactions_from_payload(PAYLOAD, "not an address!!")


def test_validate_address_rules():
    assert ce.validate_address(ADDRESS) == ADDRESS
    for bad in ("", "short", "0OIl-characters", "a" * 100):
        with pytest.raises(ce.ExplorerError):
            ce.validate_address(bad)


def test_fetch_rawaddr_builds_url_and_parses(monkeypatch):
    captured = {}

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        return FakeResp(json.dumps(PAYLOAD).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    data = ce.fetch_rawaddr(ADDRESS)
    assert data["txs"] == PAYLOAD["txs"]
    assert ADDRESS in captured["url"] and captured["url"].startswith(
        "https://blockchain.info/rawaddr/")
    assert "cors=true" in captured["url"]


def test_fetch_rawaddr_network_error_is_explorer_error(monkeypatch):
    def fake_urlopen(req, timeout=20):
        raise OSError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ce.ExplorerError):
        ce.fetch_rawaddr(ADDRESS)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "ce.db"))
    return TestClient(app)


def test_api_import_crypto_explorer(client, monkeypatch):
    monkeypatch.setattr(ce, "fetch_rawaddr",
                        lambda address, base_url="https://blockchain.info":
                        PAYLOAD)
    acc = client.post("/api/accounts", json={"name": "Wallet", "currency": "USD"}).json()["id"]
    r = client.post("/api/import/crypto-explorer",
                    json={"account_id": acc, "address": ADDRESS})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 3
    txs = client.get(f"/api/transactions?account_id={acc}").json()
    assert [(t["type"], t["ticker"]) for t in txs] == [
        ("buy", "BTC"), ("sell", "BTC"), ("fee", "BTC")]
    assets = client.get("/api/assets").json()
    kinds = {a["ticker"]: (a["kind"], a["name"]) for a in assets}
    assert kinds["BTC"] == ("crypto", "bitcoin")  # CoinGecko id wired in


def test_api_import_bad_address_is_422_and_unknown_account_404(client):
    acc = client.post("/api/accounts", json={"name": "W", "currency": "USD"}).json()["id"]
    assert client.post("/api/import/crypto-explorer",
                       json={"account_id": acc, "address": "!!!bad"}).status_code == 422
    assert client.post("/api/import/crypto-explorer",
                       json={"account_id": 999999, "address": ADDRESS}).status_code == 404


def test_imported_ledger_valuates_after_backfill(client, monkeypatch):
    """Full loop: import -> snapshot prices -> portfolio value reflects qty."""
    monkeypatch.setattr(ce, "fetch_rawaddr",
                        lambda address, base_url="https://blockchain.info":
                        {"txs": [{"hash": "dd44" * 8, "time": 1700000000,
                                  "result": 50_000_000}]})
    acc = client.post("/api/accounts", json={"name": "W", "currency": "USD"}).json()["id"]
    client.post("/api/import/crypto-explorer",
                json={"account_id": acc, "address": ADDRESS})
    client.post("/api/prices",
                params={"ticker": "BTC", "date": "2023-11-14", "price": 37000.0,
                        "currency": "USD"})
    val = client.get(f"/api/portfolio?account_id={acc}&as_of=2023-11-14").json()
    assert val["market"] == 18500.0  # 0.5 BTC * 37000
