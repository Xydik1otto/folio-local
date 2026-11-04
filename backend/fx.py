# Currency conversion built on the ECB daily reference rates.
# ECB publishes EUR-base rates: 1 EUR = rate[currency].
# Free source, no API key: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml
from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET
import urllib.request

from .db import connect

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"


def fetch_ecb_rates(url: str = ECB_URL) -> dict[str, float]:
    """Fetch today's ECB reference rates. Returns {'EUR': 1.0, 'USD': 1.08, ...}."""
    with urllib.request.urlopen(url, timeout=15) as resp:
        tree = ET.parse(resp)
    ns = {"e": "http://www.ecb.europa.eu/vocabulary/2002-08-01/eurofxref"}
    rates: dict[str, float] = {"EUR": 1.0}
    for cube in tree.getroot().iter():
        tag = cube.tag.split("}")[-1]
        if tag == "Cube" and cube.get("currency") and cube.get("rate"):
            rates[cube.get("currency")] = float(cube.get("rate"))
    del ns
    return rates


def store_rates(conn, date: str, rates: dict[str, float]) -> None:
    with conn:
        for cur, rate in rates.items():
            conn.execute(
                "INSERT OR REPLACE INTO fx_rates(date, currency, rate_to_eur) VALUES (?,?,?)",
                (date, cur, rate),
            )


def load_rates(conn, date: str) -> dict[str, float]:
    """Rates stored for the latest available date <= `date`. Empty dict if none."""
    row = conn.execute(
        "SELECT MAX(date) AS d FROM fx_rates WHERE date <= ?", (date,)
    ).fetchone()
    if not row or row["d"] is None:
        return {}
    rows = conn.execute(
        "SELECT currency, rate_to_eur FROM fx_rates WHERE date = ?", (row["d"],)
    ).fetchall()
    return {r["currency"]: r["rate_to_eur"] for r in rows}


def to_eur(amount: float, currency: str, rates: dict[str, float]) -> float:
    """Convert `amount` in `currency` to EUR given EUR-base rates."""
    cur = currency.upper()
    if cur == "EUR":
        return amount
    if cur not in rates:
        raise ValueError(f"no FX rate for {cur}")
    return amount / rates[cur]


def convert(amount: float, src: str, dst: str, rates: dict[str, float]) -> float:
    """Convert amount from currency src to currency dst (both vs EUR base)."""
    s, d = src.upper(), dst.upper()
    if s == d:
        return amount
    if s == "EUR":
        return amount * rates[d]
    if d == "EUR":
        return amount / rates[s]
    return amount / rates[s] * rates[d]
