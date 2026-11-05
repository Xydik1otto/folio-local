# Панель попереджень: дані, які ламають оцінку портфеля.
#
# Три категорії:
#  * missing_price  — buy/sell без ціни (позиція не може бути оцінена);
#  * missing_fx     — транзакція в валюті, відмінній від валюти рахунку,
#                     без збереженого курсу на ту дату;
#  * no_price_data / stale_price — тікер у позиції без котирувань або
#                     з котируваннями старшими за STALE_DAYS днів.
from __future__ import annotations

import datetime as dt

from . import fx as fxmod
from .db import account_transactions, latest_price

STALE_DAYS = 30


def collect_warnings(conn, account_id: int, as_of: str | None = None) -> dict:
    account = conn.execute(
        "SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        raise ValueError(f"account {account_id} not found")
    base = account["currency"].upper()
    as_of = as_of or dt.date.today().isoformat()
    items: list[dict] = []

    for t in account_transactions(conn, account_id):
        cur = (t["currency"] or base).upper()
        if t["type"] in ("buy", "sell") and not t["price"]:
            items.append({
                "type": "missing_price", "severity": "error",
                "date": t["date"], "ticker": t["ticker"], "tx_id": t["id"],
                "message": f"{t['type']} {t['ticker']} на {t['date']} без ціни"
                           " — лот не потрапить у собівартість",
            })
        if cur != base:
            rates = fxmod.load_rates(conn, t["date"])
            if not rates or cur not in rates:
                items.append({
                    "type": "missing_fx", "severity": "error",
                    "date": t["date"], "currency": cur, "tx_id": t["id"],
                    "message": f"немає курсу {cur} на {t['date']} "
                               f"(рахунок у {base}) — конвертація неможлива",
                })

    # тікери в поточній позиції (якщо курсів бракує, ledger падає —
    # ці пропуски вже повідомлені вище як missing_fx)
    from . import portfolio
    try:
        _, events = portfolio.ledger(conn, account_id)
        positions = events[-1]["positions"] if events else {}
    except (KeyError, ValueError):
        positions = {}
    for ticker, qty in sorted(positions.items()):
        if abs(qty) < 1e-12:
            continue
        snap = latest_price(conn, ticker, as_of)
        if snap is None:
            items.append({
                "type": "no_price_data", "severity": "error",
                "ticker": ticker, "quantity": qty,
                "message": f"тікер {ticker} у позиції, але жодного snapshot "
                           f"цін на {as_of}",
            })
        else:
            age = (dt.date.fromisoformat(as_of)
                   - dt.date.fromisoformat(snap["date"])).days
            if age > STALE_DAYS:
                items.append({
                    "type": "stale_price", "severity": "warning",
                    "ticker": ticker, "last_date": snap["date"],
                    "age_days": age,
                    "message": f"котирування {ticker} станом на "
                               f"{snap['date']} ({age} дн. тому)",
                })

    items.sort(key=lambda w: (w["severity"] != "error", w.get("date", ""),
                              w.get("ticker", "")))
    return {"account_id": account_id, "as_of": as_of,
            "count": len(items), "warnings": items}
