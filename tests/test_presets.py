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
        preset_by_name("does_not_exist")


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


# --- v1.0.0: Trade Republic, DEGIRO, Fidelity, Tinkoff-format -----------------

TR_CSV = (
    "Datum,ISIN,Typ,Stück,Preis,Währung,Gebühr\n"
    "15.01.2024,US0378331005,Kauf,10,190.5,EUR,1.00\n"
    "01.02.2024,US5949181045,Verkauf,5,410.0,EUR,1.00\n"
)

DEGIRO_CSV = (
    "Date,Product,ISIN,Type,Quantity,Price,Currency,Fees\n"
    "15-01-2024,Vanguard FTSE All-World,IE00B3RBWN25,buy,3,110.5,EUR,1.00\n"
    "01-02-2024,Vanguard FTSE All-World,IE00B3RBWN25,sell,1,115.0,EUR,1.00\n"
)

FIDELITY_CSV = (
    "Run Date,Action,Symbol,Quantity,Price ($),Fees ($),Currency\n"
    "01/15/2024,Buy,MSFT,10,410.0,0.65,USD\n"
    "02/01/2024,Sell,AAPL,5,190.5,0.65,USD\n"
    "02/05/2024,Dividend,KO,,,,USD\n"
)

TINKOFF_CSV = (
    "Operation date,Ticker,Product name,Type,Quantity,Price,Currency,Broker commission\n"
    "15.01.2024,AAPL,Apple Inc.,buy,10,190.5,USD,1.20\n"
    "01.02.2024,MSFT,Microsoft Corp.,sell,5,410.0,USD,0.85\n"
)


def test_new_preset_names_present():
    assert {"trade_republic", "degiro", "fidelity", "tinkoff_generic"} <= set(PRESETS)


def test_trade_republic_end_to_end(conn):
    n = import_with_preset(conn, 1, TR_CSV, "trade_republic")
    assert n == 2
    rows = list(conn.execute("SELECT type, date, quantity, currency FROM transactions ORDER BY date"))
    assert rows[0]["type"] == "buy" and rows[0]["date"] == "2024-01-15"  # DD.MM.YYYY
    assert rows[0]["currency"] == "EUR"
    assert rows[1]["type"] == "sell"


def test_degiro_end_to_end(conn):
    n = import_with_preset(conn, 1, DEGIRO_CSV, "degiro")
    assert n == 2
    rows = list(conn.execute(
        "SELECT a.ticker, a.name, t.type, t.date FROM transactions t "
        "JOIN assets a ON a.id = t.asset_id ORDER BY t.date"))
    assert rows[0]["ticker"] == "IE00B3RBWN25"
    assert rows[0]["name"] == "Vanguard FTSE All-World"
    assert rows[0]["date"] == "2024-01-15"  # DD-MM-YYYY


def test_fidelity_end_to_end(conn):
    n = import_with_preset(conn, 1, FIDELITY_CSV, "fidelity")
    assert n == 3
    types = [r["type"] for r in conn.execute(
        "SELECT type FROM transactions ORDER BY id")]
    assert types == ["buy", "sell", "dividend"]
    date = conn.execute("SELECT date FROM transactions ORDER BY id LIMIT 1").fetchone()[0]
    assert date == "2024-01-15"  # MM/DD/YYYY


def test_fidelity_dividend_has_no_quantity(conn):
    import_with_preset(conn, 1, FIDELITY_CSV, "fidelity")
    row = conn.execute(
        "SELECT quantity, amount FROM transactions WHERE type = 'dividend'").fetchone()
    assert row["quantity"] is None
    assert row["amount"] is None  # dividend without amount is stored as NULL


def test_tinkoff_generic_end_to_end(conn):
    n = import_with_preset(conn, 1, TINKOFF_CSV, "tinkoff_generic")
    assert n == 2
    rows = list(conn.execute(
        "SELECT a.ticker, t.type, t.date, t.fees, t.currency FROM transactions t "
        "JOIN assets a ON a.id = t.asset_id ORDER BY t.date"))
    assert rows[0]["ticker"] == "AAPL" and rows[0]["date"] == "2024-01-15"
    assert rows[0]["fees"] == 1.20 and rows[0]["currency"] == "USD"
    assert rows[1]["type"] == "sell"


def test_tinkoff_preset_has_no_russian_headers():
    # Жорстке правило власника: ніколи не додавати російську локалізацію.
    import re
    for col in PRESETS["tinkoff_generic"]["mapping"].values():
        assert not re.search(r"[\u0400-\u04FF]", col), col
