# Portfolio valuation, P/L, XIRR and TWR computed from stored transactions.
#
# Design decisions (the part Ghostfolio gets wrong):
#  * Every money movement is converted to the ACCOUNT currency at the moment it
#    happens, using the FX rate stored for that date — so the cash ledger and
#    the valuation series are always in ONE currency.
#  * XIRR uses only EXTERNAL flows: deposits (negative), withdrawals (positive)
#    and the current market value (positive, today). Buys/sells/dividends/fees
#    are internal shuffling and must NOT appear in the XIRR input.
#  * TWR is chained between external flow dates only.
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from . import fx as fxmod
from . import math_finance
from .db import account_transactions, latest_price


def _rate(conn, date: str) -> dict[str, float]:
    rates = fxmod.load_rates(conn, date)
    if not rates:
        rates = {"EUR": 1.0}
    return rates


def _to_account_ccy(conn, amount: float, currency: str, date: str, base: str) -> float:
    if currency.upper() == base.upper():
        return amount
    rates = _rate(conn, date)
    if not rates:
        raise ValueError(f"no FX rates stored on or before {date}")
    return fxmod.convert(amount, currency, base, rates)


def ledger(conn, account_id: int):
    """Replay transactions into (positions, cash) series in account currency.

    Returns list of event dicts sorted by date: each has date, cash (after),
    positions {ticker: qty}, and the raw transaction. Positions/cash are the
    running state AFTER that transaction.
    """
    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        raise ValueError(f"account {account_id} not found")
    base = account["currency"].upper()

    cash = 0.0
    positions: dict[str, float] = defaultdict(float)
    events = []
    for t in account_transactions(conn, account_id):
        cur = t["currency"].upper()
        day = {
            "date": t["date"], "type": t["type"], "ticker": t["ticker"],
            "quantity": t["quantity"], "price": t["price"], "amount": t["amount"],
            "currency": cur, "fees": t["fees"], "id": t["id"],
        }
        if t["type"] == "deposit":
            cash += _to_account_ccy(conn, t["amount"] or 0.0, cur, t["date"], base)
        elif t["type"] == "withdrawal":
            cash -= _to_account_ccy(conn, t["amount"] or 0.0, cur, t["date"], base)
        elif t["type"] in ("buy", "sell"):
            qty = t["quantity"] or 0.0
            price = t["price"] or 0.0
            gross = qty * price
            total = gross + (t["fees"] or 0.0)
            sign = 1.0 if t["type"] == "buy" else -1.0
            positions[t["ticker"]] += sign * qty
            cash -= sign * _to_account_ccy(conn, total, cur, t["date"], base)
        elif t["type"] == "dividend":
            cash += _to_account_ccy(conn, (t["amount"] or 0.0) - (t["fees"] or 0.0),
                                    cur, t["date"], base)
        elif t["type"] == "fee":
            cash -= _to_account_ccy(conn, t["amount"] or 0.0, cur, t["date"], base)
        day["cash"] = cash
        day["positions"] = dict(positions)
        events.append(day)
    return account, events


def value_on_date(conn, account_id: int, date: str) -> dict:
    """Portfolio value (cash + market) in account currency on `date`."""
    account, events = ledger(conn, account_id)
    base = account["currency"].upper()
    prior = [e for e in events if e["date"] <= date]
    if not prior:
        return {"date": date, "cash": 0.0, "market": 0.0, "total": 0.0,
                "currency": base, "positions": {}}
    state = prior[-1]
    rates = _rate(conn, date) or {"EUR": 1.0}
    market = 0.0
    valued: dict[str, float] = {}
    for ticker, qty in state["positions"].items():
        if abs(qty) < 1e-12:
            continue
        asset_row = conn.execute(
            "SELECT currency FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()
        snap = latest_price(conn, ticker, date)
        if snap is None:
            raise ValueError(f"no price snapshot for {ticker} on or before {date}")
        px = fxmod.convert(snap["price"], snap["currency"], base, rates)
        market += qty * px
        valued[ticker] = qty * px
    cash = state["cash"]
    return {"date": date, "cash": round(cash, 2), "market": round(market, 2),
            "total": round(cash + market, 2), "currency": base, "positions": valued}


def external_flows(conn, account_id: int) -> list[tuple[dt.date, float]]:
    """XIRR input: deposits negative, withdrawals positive (account currency)."""
    _, events = ledger(conn, account_id)
    flows = []
    for e in events:
        if e["type"] == "deposit":
            flows.append((dt.date.fromisoformat(e["date"]),
                          -(e["amount"] or 0.0)))
        elif e["type"] == "withdrawal":
            flows.append((dt.date.fromisoformat(e["date"]),
                          (e["amount"] or 0.0)))
    return flows


def portfolio_xirr(conn, account_id: int, as_of: str | None = None) -> float | None:
    account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    flows = external_flows(conn, account_id)
    end = as_of or dt.date.today().isoformat()
    val = value_on_date(conn, account_id, end)
    if val["total"] > 0:
        flows.append((dt.date.fromisoformat(end), val["total"]))
    try:
        return math_finance.xirr(flows)
    except ValueError:
        return None


def twr_series(conn, account_id: int, start: str, end: str) -> float | None:
    """TWR over [start, end]: valuation at each external-flow date plus end."""
    flows = external_flows(conn, account_id)
    dates = sorted({f[0].isoformat() for f in flows if start <= f[0].isoformat() <= end})
    if not dates or dates[0] > start:
        dates = [start] + dates
    if dates[-1] < end:
        dates.append(end)
    pts = []
    for i, d in enumerate(dates):
        v = value_on_date(conn, account_id, d)["total"]
        # Flows on the FIRST date are opening capital, not an adjustment.
        # external_flows uses the XIRR sign (deposit = negative); TWR wants
        # money ADDED to the portfolio as positive, hence the sign flip.
        flow = 0.0 if i == 0 else -sum(a for date_, a in flows
                                       if date_.isoformat() == d)
        pts.append((dt.date.fromisoformat(d), v, flow))
    try:
        return math_finance.twr(pts)
    except ValueError:
        return None
