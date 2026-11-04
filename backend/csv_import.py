# CSV import with a FIXED column layout (column-mapping UI planned for v1).
# Required header: date,ticker,action,quantity,price,currency[,fees][,name][,kind]
# action: buy|sell|dividend|fee|deposit|withdrawal
from __future__ import annotations

import csv
import io

from .db import upsert_asset

REQUIRED = ["date", "ticker", "action", "quantity", "price", "currency"]
ACTIONS = {"buy", "sell", "dividend", "fee", "deposit", "withdrawal"}
KINDS = {"stock", "etf", "crypto", "cash"}


class ImportRowError(ValueError):
    pass


def parse_csv(text: str) -> list[dict]:
    """Validate + normalise rows into transaction dicts. Raises ImportRowError."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportRowError("empty CSV")
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        raise ImportRowError(f"missing columns: {', '.join(missing)}")

    out = []
    for i, row in enumerate(reader, start=2):  # header is line 1
        action = (row.get("action") or "").strip().lower()
        if action not in ACTIONS:
            raise ImportRowError(f"line {i}: unknown action {action!r}")
        ticker = (row.get("ticker") or "").strip()
        currency = (row.get("currency") or "EUR").strip().upper()
        date = (row.get("date") or "").strip()
        if len(date) != 10 or date[4] != "-" or date[7] != "-":
            raise ImportRowError(f"line {i}: date must be YYYY-MM-DD, got {date!r}")

        def num(key: str) -> float | None:
            raw = (row.get(key) or "").strip()
            if raw == "":
                return None
            try:
                return float(raw.replace(",", "."))
            except ValueError:
                raise ImportRowError(f"line {i}: bad number in {key}: {raw!r}")

        quantity, price, fees = num("quantity"), num("price"), num("fees")
        amount: float | None
        if action in ("deposit", "withdrawal", "fee"):
            amount = price if price is not None else quantity
            quantity = None
            price = None
            ticker = ""  # cash movements carry no asset
        elif action == "dividend":
            amount = price if price is not None else quantity
            quantity = None
            price = None
            if not ticker:
                raise ImportRowError(f"line {i}: dividend needs a ticker")
        else:  # buy/sell
            if quantity is None or price is None:
                raise ImportRowError(f"line {i}: {action} needs quantity and price")
            if not ticker:
                raise ImportRowError(f"line {i}: {action} needs a ticker")
            amount = quantity * price + (fees or 0.0)
        out.append({
            "date": date, "ticker": ticker, "action": action,
            "quantity": quantity, "price": price, "amount": amount,
            "fees": fees or 0.0, "currency": currency,
            "name": (row.get("name") or "").strip() or None,
            "kind": (row.get("kind") or "stock").strip().lower(),
        })
    return out


def import_csv(conn, account_id: int, text: str) -> int:
    """Parse and persist rows. Returns number of transactions imported."""
    rows = parse_csv(text)
    with conn:
        for r in rows:
            asset_id = None
            if r["ticker"]:
                kind = r["kind"] if r["kind"] in KINDS else "stock"
                asset_id = upsert_asset(conn, r["ticker"], r["name"], kind, r["currency"])
            conn.execute(
                "INSERT INTO transactions(account_id, asset_id, type, date, quantity,"
                " price, amount, fees, currency, note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (account_id, asset_id, r["action"], r["date"], r["quantity"],
                 r["price"], r["amount"], r["fees"], r["currency"], r["name"]),
            )
    return len(rows)
