# Column-mapping importer: arbitrary broker CSV -> canonical layout -> import.
import pytest

from backend.csv_import import (ImportRowError, apply_mapping, csv_columns,
                                convert_date, import_mapped, parse_csv)
from backend.db import connect, store_price


@pytest.fixture()
def conn():
    return connect(":memory:")


BROKER_CSV = (
    "TradeDate,Symbol,Quantity,TradePrice,Currency,Commission\n"
    "20240115,AAPL,10,190.5,USD,1.20\n"
    "20240201,MSFT,5,410.0,USD,0.85\n"
)


def test_convert_date_supported_formats():
    assert convert_date("2024-01-15") == "2024-01-15"          # ISO auto
    assert convert_date("20240115") == "2024-01-15"            # bare YYYYMMDD
    assert convert_date("15.01.2024", "DD.MM.YYYY") == "2024-01-15"
    assert convert_date("01/15/2024", "MM/DD/YYYY") == "2024-01-15"
    assert convert_date("15/01/2024", "DD/MM/YYYY") == "2024-01-15"
    with pytest.raises(ImportRowError):
        convert_date("not-a-date", "DD.MM.YYYY")


def test_csv_columns_preview():
    info = csv_columns(BROKER_CSV)
    assert info["columns"] == ["TradeDate", "Symbol", "Quantity",
                               "TradePrice", "Currency", "Commission"]
    assert info["row_count"] == 2
    assert info["sample"][0][1] == "AAPL"
    with pytest.raises(ImportRowError):
        csv_columns("")  # empty CSV


def test_apply_mapping_and_parse_roundtrip():
    csv_text = (
        "Date,Ticker,Side,Qty,Price,Ccy,Fee,Security Name,Type\n"
        "20240115,AAPL,Buy,10,190.5,USD,1.20,Apple Inc,stock\n"
        "20240201,MSFT,Sell,5,410.0,USD,0.85,Microsoft,stock\n"
    )
    mapping = {"date": "Date", "ticker": "Ticker", "action": "Side",
               "quantity": "Qty", "price": "Price", "currency": "Ccy",
               "fees": "Fee", "name": "Security Name", "kind": "Type"}
    canon = apply_mapping(csv_text, mapping, date_format="YYYYMMDD",
                          action_map={"buy": "buy", "sell": "sell"})
    rows = parse_csv(canon)
    assert len(rows) == 2
    assert rows[0]["date"] == "2024-01-15"
    assert rows[0]["action"] == "buy"
    assert rows[1]["action"] == "sell"
    assert rows[0]["amount"] == pytest.approx(10 * 190.5 + 1.20)
    assert rows[0]["name"] == "Apple Inc"


def test_apply_mapping_missing_required_field_raises():
    mapping = {"date": "TradeDate", "ticker": "Symbol", "quantity": "Quantity",
               "price": "TradePrice", "currency": "Currency"}  # no 'action'
    with pytest.raises(ImportRowError, match="action"):
        apply_mapping(BROKER_CSV, mapping)


def test_apply_mapping_unknown_column_raises():
    mapping = {"date": "TradeDate", "ticker": "Symbol", "action": "Side",
               "quantity": "Quantity", "price": "TradePrice",
               "currency": "Currency"}
    with pytest.raises(ImportRowError, match="Side"):
        apply_mapping(BROKER_CSV, mapping)  # 'Side' not in this file's header


def test_apply_mapping_duplicate_column_rejected():
    mapping = {"date": "TradeDate", "ticker": "Symbol", "action": "Symbol",
               "quantity": "Quantity", "price": "TradePrice",
               "currency": "Currency", "fees": "Symbol"}
    with pytest.raises(ImportRowError, match="same column"):
        apply_mapping(BROKER_CSV, mapping)


def test_apply_mapping_unknown_target_field_raises():
    mapping = {"date": "TradeDate", "bogus": "Symbol"}
    with pytest.raises(ImportRowError, match="bogus"):
        apply_mapping(BROKER_CSV, mapping)


def test_import_mapped_end_to_end(conn):
    conn.execute("INSERT INTO accounts(name, currency) VALUES ('T', 'EUR')")
    store_price(conn, "AAPL", "2024-01-15", 190.5, "USD")
    csv_text = (
        "Date,Ticker,Side,Qty,Price,Ccy,Fee\n"
        "20240115,AAPL,Buy,10,190.5,USD,1.20\n"
    )
    mapping = {"date": "Date", "ticker": "Ticker", "action": "Side",
               "quantity": "Qty", "price": "Price", "currency": "Ccy",
               "fees": "Fee"}
    n = import_mapped(conn, 1, csv_text, mapping, date_format="YYYYMMDD",
                      action_map={"buy": "buy"})
    assert n == 1
    tx = conn.execute("SELECT type, quantity, price, fees, currency "
                      "FROM transactions").fetchone()
    assert tx["type"] == "buy"
    assert tx["quantity"] == 10 and tx["price"] == 190.5
    assert tx["fees"] == pytest.approx(1.20)
    assert tx["currency"] == "USD"


def test_mapped_import_via_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "map.db"))
    client = TestClient(app)
    acc = client.post("/api/accounts", json={"name": "T"}).json()["id"]

    r = client.post("/api/import/preview", json={"account_id": acc, "csv_text": BROKER_CSV})
    assert r.status_code == 200
    assert r.json()["columns"][0] == "TradeDate"

    # mapping referencing a column the file does not have -> 400
    bad = {"date": "TradeDate", "ticker": "Symbol", "action": "Action",
           "quantity": "Quantity", "price": "TradePrice", "currency": "Currency"}
    r = client.post("/api/import/mapped", json={
        "account_id": acc, "csv_text": BROKER_CSV, "mapping": bad,
        "date_format": "YYYYMMDD"})
    assert r.status_code == 400

    side_csv = (
        "TradeDate,Symbol,Side,Quantity,TradePrice,Currency,Commission\n"
        "20240115,AAPL,Buy,10,190.5,USD,1.20\n"
        "20240201,MSFT,Sell,5,410.0,USD,0.85\n"
    )
    mapping = {"date": "TradeDate", "ticker": "Symbol", "action": "Side",
               "quantity": "Quantity", "price": "TradePrice",
               "currency": "Currency", "fees": "Commission"}
    r = client.post("/api/import/mapped", json={
        "account_id": acc, "csv_text": side_csv, "mapping": mapping,
        "date_format": "YYYYMMDD", "action_map": {"buy": "buy", "sell": "sell"}})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 2
    txs = client.get("/api/transactions", params={"account_id": acc}).json()
    assert {t["type"] for t in txs} == {"buy", "sell"}
