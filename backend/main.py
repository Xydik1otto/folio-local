# FastAPI application: REST API + static frontend for folio-local.
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import csv_import, fx as fxmod, portfolio, prices
from .db import DB_PATH, account_transactions, connect, get_asset, upsert_asset

app = FastAPI(title="folio-local", version="0.3.0",
              description="Self-hosted portfolio tracker with correct TWR/XIRR math")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def get_conn():
    return connect(os.environ.get("FOLIO_DB", DB_PATH))


# --- request models ----------------------------------------------------------

class AccountIn(BaseModel):
    name: str
    currency: str = "EUR"
    cash: float = 0.0


class TransactionIn(BaseModel):
    account_id: int
    type: str = Field(pattern="^(buy|sell|dividend|fee|deposit|withdrawal)$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    ticker: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float | None = None
    fees: float = 0.0
    currency: str = "EUR"
    note: str | None = None


class FxIn(BaseModel):
    date: str
    rates: dict[str, float]  # EUR base: {"USD": 1.08, ...}


class ImportIn(BaseModel):
    account_id: int
    csv_text: str


class ImportMappedIn(BaseModel):
    account_id: int
    csv_text: str
    mapping: dict[str, str] | None = None  # canonical field -> CSV column header
    date_format: str | None = None   # see csv_import.DATE_FORMATS
    action_map: dict[str, str] | None = None  # raw action -> canonical action
    preset: str | None = None        # broker preset (overrides mapping)


class BackfillIn(BaseModel):
    ticker: str
    start: str
    end: str


# --- API ---------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/accounts")
def create_account(body: AccountIn):
    conn = get_conn()
    with conn:
        cur = conn.execute(
            "INSERT INTO accounts(name, currency, cash) VALUES (?,?,?)",
            (body.name, body.currency.upper(), body.cash),
        )
    return {"id": cur.lastrowid, **body.model_dump()}


@app.get("/api/accounts")
def list_accounts():
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM accounts").fetchall()]


@app.get("/api/assets")
def list_assets():
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM assets").fetchall()]


@app.get("/api/transactions")
def list_transactions(account_id: int):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone():
        raise HTTPException(404, "account not found")
    return [dict(r) for r in account_transactions(conn, account_id)]


@app.post("/api/transactions")
def add_transaction(body: TransactionIn):
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM accounts WHERE id = ?", (body.account_id,)).fetchone():
        raise HTTPException(404, "account not found")
    asset_id = None
    if body.ticker:
        asset = get_asset(conn, body.ticker.upper())
        if asset:
            asset_id = asset["id"]
        else:
            kind = "crypto" if body.type in ("buy", "sell") and body.note == "crypto" else "stock"
            asset_id = upsert_asset(conn, body.ticker.upper(), None, kind, body.currency)
    with conn:
        cur = conn.execute(
            "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
            " price, amount, fees, currency, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (body.account_id, asset_id, body.type, body.date, body.quantity,
             body.price, body.amount, body.fees, body.currency.upper(), body.note),
        )
    return {"id": cur.lastrowid, **body.model_dump()}


@app.post("/api/fx")
def store_fx(body: FxIn):
    conn = get_conn()
    rates = {"EUR": 1.0, **body.rates}
    fxmod.store_rates(conn, body.date, rates)
    return {"stored": body.date, "currencies": sorted(rates)}


@app.get("/api/fx")
def get_fx(date: str | None = None):
    conn = get_conn()
    date = date or dt.date.today().isoformat()
    return {"date": date, "rates": fxmod.load_rates(conn, date)}


@app.post("/api/fx/refresh")
def refresh_fx():
    """Pull today's ECB reference rates (free, no key)."""
    try:
        rates = fxmod.fetch_ecb_rates()
    except OSError as e:
        raise HTTPException(502, f"ECB fetch failed: {e}")
    conn = get_conn()
    fxmod.store_rates(conn, dt.date.today().isoformat(), rates)
    return {"date": dt.date.today().isoformat(), "currencies": sorted(rates)}


@app.post("/api/prices")
def add_price(ticker: str, date: str, price: float, currency: str = "USD"):
    conn = get_conn()
    from .db import store_price
    store_price(conn, ticker.upper(), date, price, currency.upper())
    return {"ok": True}


@app.post("/api/prices/update")
def update_prices(tickers: list[str]):
    """Fetch latest close from Stooq (stocks) / CoinGecko (crypto)."""
    conn = get_conn()
    return prices.update_prices(conn, [t.upper() for t in tickers])


@app.get("/api/portfolio")
def get_portfolio(account_id: int, as_of: str | None = None):
    conn = get_conn()
    try:
        val = portfolio.value_on_date(conn, account_id, as_of or dt.date.today().isoformat())
        x = portfolio.portfolio_xirr(conn, account_id, as_of)
    except ValueError as e:
        raise HTTPException(400, str(e))
    flows = portfolio.external_flows(conn, account_id)
    deposits = sum(-a for _, a in flows if a < 0)
    withdrawals = sum(a for _, a in flows if a > 0)
    return {**val, "xirr": x,
            "pnl": round(val["total"] - (deposits - withdrawals), 2)}


@app.get("/api/portfolio/history")
def portfolio_history(account_id: int, start: str, end: str):
    conn = get_conn()
    try:
        start_d = dt.date.fromisoformat(start)
        end_d = dt.date.fromisoformat(end)
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD")
    points = []
    _, events = portfolio.ledger(conn, account_id)
    dates = sorted({e["date"] for e in events if start <= e["date"] <= end} | {start, end})
    for d in dates:
        try:
            points.append(portfolio.value_on_date(conn, account_id, d))
        except ValueError:
            continue
    return {"start": start, "end": end, "currency": conn.execute(
        "SELECT currency FROM accounts WHERE id = ?", (account_id,)).fetchone()["currency"],
        "points": points}


@app.get("/api/portfolio/twr")
def portfolio_twr(account_id: int, start: str, end: str):
    conn = get_conn()
    t = portfolio.twr_series(conn, account_id, start, end)
    if t is None:
        raise HTTPException(400, "cannot compute TWR for this range")
    return {"start": start, "end": end, "twr": t}


@app.post("/api/import/csv")
def import_csv(body: ImportIn):
    conn = get_conn()
    try:
        n = csv_import.import_csv(conn, body.account_id, body.csv_text)
    except csv_import.ImportRowError as e:
        raise HTTPException(400, str(e))
    return {"imported": n}


@app.post("/api/import/preview")
def import_preview(body: ImportIn):
    """Column headers + sample rows, so the UI can render the mapping wizard."""
    try:
        return csv_import.csv_columns(body.csv_text)
    except csv_import.ImportRowError as e:
        raise HTTPException(400, str(e))


@app.get("/api/import/presets")
def import_presets():
    """Known broker CSV templates: {name, label, mapping, date_format}."""
    return [{"name": name, **{k: v for k, v in p.items()}}
            for name, p in csv_import.PRESETS.items()]


@app.post("/api/import/mapped")
def import_mapped(body: ImportMappedIn):
    """Import an arbitrary broker CSV using a user-supplied column mapping
    or a broker preset."""
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM accounts WHERE id = ?",
                        (body.account_id,)).fetchone():
        raise HTTPException(404, "account not found")
    if body.preset:
        try:
            n = csv_import.import_with_preset(conn, body.account_id,
                                              body.csv_text, body.preset)
        except csv_import.ImportRowError as e:
            raise HTTPException(400, str(e))
        return {"imported": n, "preset": body.preset}
    if not body.mapping:
        raise HTTPException(400, "provide 'mapping' or 'preset'")
    try:
        n = csv_import.import_mapped(conn, body.account_id, body.csv_text,
                                     body.mapping, body.date_format,
                                     body.action_map)
    except csv_import.ImportRowError as e:
        raise HTTPException(400, str(e))
    return {"imported": n}


@app.get("/api/holdings")
def get_holdings(account_id: int, as_of: str | None = None):
    """Позиції рахунку: кількість, середня ціна, поточна вартість, P/L."""
    conn = get_conn()
    try:
        return portfolio.holdings(conn, account_id, as_of)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/portfolio/allocation")
def portfolio_allocation(account_id: int, as_of: str | None = None):
    """Розподіл вартості по класах активів + кеш (для pie-діаграми)."""
    conn = get_conn()
    try:
        return portfolio.allocation(conn, account_id, as_of)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/dividends")
def dividends(account_id: int, year: int | None = None):
    """Дивідендний календар: суми за місяцями й тікерами."""
    conn = get_conn()
    try:
        return portfolio.dividend_summary(conn, account_id, year)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tax/preview")
def tax_preview(account_id: int, year: int, method: str = "fifo"):
    """Реалізовані прибутки за рік, метод FIFO/LIFO (податковий прев'ю)."""
    conn = get_conn()
    try:
        return portfolio.realized_gains(conn, account_id, year, method)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/prices/backfill")
def backfill(body: BackfillIn):
    """Store daily price snapshots for a ticker over a date range (Stooq)."""
    conn = get_conn()
    try:
        return prices.backfill_prices(conn, body.ticker, body.start, body.end)
    except ValueError:
        raise HTTPException(400, "start/end must be YYYY-MM-DD")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
