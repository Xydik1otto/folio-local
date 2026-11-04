# Free price data: Stooq CSV (stocks/ETFs) + CoinGecko (crypto). No API keys.
from __future__ import annotations

import csv
import io
import urllib.request

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"


def fetch_stooq_latest(symbol: str) -> tuple[str, float] | None:
    """Return (date, close) of the latest row of Stooq's daily CSV, or None."""
    url = STOOQ_URL.format(symbol=symbol)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "folio-local/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8", "replace")
    except OSError:
        return None
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return None
    last = rows[-1]
    try:
        return last["Date"], float(last["Close"])
    except (KeyError, ValueError):
        return None


def fetch_coingecko_price(coin_id: str) -> tuple[str, float] | None:
    """Return (today, usd_price) for a CoinGecko coin id, or None on failure."""
    url = COINGECKO_URL.format(ids=coin_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "folio-local/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if coin_id not in data or "usd" not in data[coin_id]:
        return None
    import datetime as dt
    return dt.date.today().isoformat(), float(data[coin_id]["usd"])


def update_prices(conn, tickers: list[str]) -> dict[str, float | None]:
    """Fetch latest prices for tickers and store snapshots. Stooq first, then
    CoinGecko for anything that still has no snapshot today."""
    from .db import get_asset, store_price
    results: dict[str, float | None] = {}
    for ticker in tickers:
        asset = get_asset(conn, ticker)
        quote = fetch_stooq_latest(ticker.lower())
        currency = "USD"
        if quote is None and asset and asset["kind"] == "crypto" and asset["name"]:
            quote = fetch_coingecko_price(asset["name"])  # name column stores coin id
            currency = "USD"
        if quote is None:
            results[ticker] = None
            continue
        date, price = quote
        store_price(conn, ticker, date, price, currency)
        results[ticker] = price
    return results
