# CSV import with a FIXED column layout (column-mapping UI planned for v1).
# Required header: date,ticker,action,quantity,price,currency[,fees][,name][,kind]
# action: buy|sell|dividend|fee|deposit|withdrawal
from __future__ import annotations

import csv
import datetime as dt
import io

from .db import upsert_asset

REQUIRED = ["date", "ticker", "action", "quantity", "price", "currency"]
OPTIONAL = ["fees", "name", "kind"]
CANON_FIELDS = REQUIRED + OPTIONAL
ACTIONS = {"buy", "sell", "dividend", "fee", "deposit", "withdrawal"}
KINDS = {"stock", "etf", "crypto", "cash"}

# Date formats accepted by the column-mapping importer (display name -> strptime).
DATE_FORMATS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD.MM.YYYY": "%d.%m.%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "YYYYMMDD": "%Y%m%d",
    "YYYY/MM/DD": "%Y/%m/%d",
}


class ImportRowError(ValueError):
    pass


def convert_date(raw: str, date_format: str | None = None) -> str:
    """Normalise a broker date cell to ISO YYYY-MM-DD."""
    raw = (raw or "").strip()
    if date_format:
        fmt = DATE_FORMATS.get(date_format)
        if fmt is None:
            raise ImportRowError(f"unknown date format {date_format!r}; "
                                 f"one of {', '.join(DATE_FORMATS)}")
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            raise ImportRowError(f"date {raw!r} does not match format {date_format}")
    # Default: accept plain ISO dates and bare YYYYMMDD (IBKR-style exports).
    try:
        return dt.date.fromisoformat(raw).isoformat()
    except ValueError:
        pass
    try:
        return dt.datetime.strptime(raw, "%Y%m%d").date().isoformat()
    except ValueError:
        raise ImportRowError(f"unrecognised date {raw!r}; set date_format explicitly")


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


# --- column-mapping importer (ALPHA: any broker CSV) --------------------------

def csv_columns(text: str, sample_rows: int = 5) -> dict:
    """Header + a few data rows, for the mapping UI preview."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or not any(h.strip() for h in rows[0]):
        raise ImportRowError("empty CSV")
    header = [h.strip() for h in rows[0]]
    sample = [r[: len(header)] + [""] * (len(header) - len(r))
              for r in rows[1:1 + sample_rows] if any(c.strip() for c in r)]
    n_data = sum(1 for r in rows[1:] if any(c.strip() for c in r))
    return {"columns": header, "sample": sample, "row_count": n_data}


def apply_mapping(text: str, mapping: dict[str, str],
                  date_format: str | None = None,
                  action_map: dict[str, str] | None = None) -> str:
    """Re-header an arbitrary broker CSV into the canonical column layout.

    `mapping` maps canonical field -> CSV column header, e.g.
    {"date": "TradeDate", "ticker": "Symbol", ...}. Only mapped fields are
    kept; required fields must all be present. Returns canonical CSV text.
    """
    unknown = [c for c in mapping if c not in CANON_FIELDS]
    if unknown:
        raise ImportRowError(f"unknown target fields: {', '.join(unknown)}")
    missing = [c for c in REQUIRED if c not in mapping]
    if missing:
        raise ImportRowError(f"mapping is missing required fields: {', '.join(missing)}")
    if len(set(mapping.values())) != len(mapping):
        raise ImportRowError("two canonical fields mapped to the same column")

    parsed = csv_columns(text, sample_rows=0)
    header = parsed["columns"]
    absent = [col for col in mapping.values() if col not in header]
    if absent:
        raise ImportRowError(f"columns not found in CSV: {', '.join(absent)}")
    idx = {c: header.index(col) for c, col in mapping.items()}

    out_fields = [c for c in CANON_FIELDS if c in mapping]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(out_fields)
    for raw in list(csv.reader(io.StringIO(text)))[1:]:
        if not any(c.strip() for c in raw):
            continue
        row = []
        for c in out_fields:
            i = idx[c]
            v = raw[i].strip() if i < len(raw) else ""
            if c == "date":
                v = convert_date(v, date_format)
            elif c == "action" and action_map:
                v = action_map.get(v.lower(), v)
            row.append(v)
        writer.writerow(row)
    return buf.getvalue()


def import_mapped(conn, account_id: int, text: str, mapping: dict[str, str],
                  date_format: str | None = None,
                  action_map: dict[str, str] | None = None) -> int:
    """Import an arbitrary CSV using the user's column mapping."""
    canonical = apply_mapping(text, mapping, date_format, action_map)
    return import_csv(conn, account_id, canonical)
