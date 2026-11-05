# Broker-specific CSV presets (IBKR, Revolut) for one-click import.
import pytest

from backend.csv_import import (PRESETS, ImportRowError, import_with_preset,
                                parse_csv, preset_by_name)
from backend.db import connect, upsert_asset


IBKR_CSV = (
    "TradeDate,Symbol,Side,Quantity,TradePrice,Currency,Commission\n"
    "20240115,AAPL,Buy,10,190.5,USD,1.20\n"
    "20240201,MSFT,Sell,5,410.0,USD,0.85\n"
)


@pytest.fixture()
def conn():
    c = connect(":memory:")
    c.execute("INSERT INTO accounts(name, currency) VALUES ('T', 'EUR')")
    return c


def test_every_preset_is_well_formed():
    for name, p in PRESETS.items():
        assert "label" in p and "mapping" in p, name
        for field in ("date", "ticker", "action", "quantity", "price", "currency"):
            assert field in p["mapping"], f"{name}: missing {field}"
        # date_format is either None or a key of DATE_FORMATS
        from backend.csv_import import DATE_FORMATS
        assert p["date_format"] is None or p["date_format"] in DATE_FORMATS, name


def test_preset_by_name_unknown_raises():
    assert preset_by_name("ibkr_trades")["mapping"]["date"] == "TradeDate"
    with pytest.raises(ImportRowError, match="unknown preset"):
        preset_by_name("fidelity")


def test_ibkr_preset_import_end_to_end(conn):
    n = import_with_preset(conn, 1, IBKR_CSV, "ibkr_trades")
    assert n == 2
    rows = conn.execute(
        "SELECT t.type, t.date, t.quantity, t.price, t.fees, t.currency, a.ticker "
        "FROM transactions t JOIN assets a ON a.id = t.asset_id "
        "ORDER BY t.date").fetchall()
    assert rows[0]["type"] == "buy" and rows[0]["ticker"] == "AAPL"
    assert rows[0]["date"] == "2024-01-15"           # YYYYMMDD converted
    assert rows[0]["quantity"] == 10
    assert rows[1]["type"] == "sell" and rows[1]["ticker"] == "MSFT"


def test_ibkr_preset_action_map_normalises_side(conn):
    import_with_preset(conn, 1, IBKR_CSV, "ibkr_trades")
    types = [r["type"] for r in conn.execute(
        "SELECT type FROM transactions ORDER BY id")]
    assert types == ["buy", "sell"]


def test_generic_preset_accepts_canonical_csv(conn):
    canonical = ("date,ticker,action,quantity,price,currency\n"
                 "2024-01-15,AAPL,buy,10,190.5,USD\n")
    n = import_with_preset(conn, 1, canonical, "generic")
    assert n == 1


def test_preset_against_foreign_file_fails_cleanly(conn):
    revolut_like = "Date,Ticker,Type,Quantity,Price per share,Currency,Fees\n"
    with pytest.raises(ImportRowError):
        import_with_preset(conn, 1, IBKR_CSV, "revolut_stocks")  # wrong columns
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
