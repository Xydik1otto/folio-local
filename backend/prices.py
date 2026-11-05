# Free price data: Stooq CSV (stocks/ETFs) + CoinGecko (crypto). No API keys.
from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.request

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
COINGECKO_HISTORY_URL = ("https://api.coingecko.com/api/v3/coins/{coin_id}/history"
                         "?date={dmy}&localization=false")

# Well-known crypto tickers -> CoinGecko coin ids (free API, no key).
KNOWN_COINS = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple",
    "ADA": "cardano", "DOGE": "dogecoin", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "DOT": "polkadot", "LINK": "chainlink",
    "AVAX": "avalanche-2", "MATIC": "matic-network", "TON": "the-open-network",
    "SHIB": "shiba-inu", "TRX": "tron",
}


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
    from .db import MANUAL_KINDS, get_asset, store_price
    results: dict[str, float | None] = {}
    for ticker in tickers:
        asset = get_asset(conn, ticker)
        if asset and asset["kind"] in MANUAL_KINDS:
            # bond / metal / real_estate: manual valuation only, no free feed
            results[ticker] = None
            continue
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


def fetch_stooq_history(symbol: str, start: str | None = None,
                        end: str | None = None) -> list[tuple[str, float]]:
    """Full daily history (or a date range) from Stooq's CSV endpoint.

    Raises OSError on network failure; returns [] when Stooq has no data.
    """
    url = STOOQ_URL.format(symbol=symbol)
    if start or end:
        d1 = (start or "1900-01-01").replace("-", "")
        d2 = (end or dt.date.today().isoformat()).replace("-", "")
        url += f"&d1={d1}&d2={d2}"
    req = urllib.request.Request(url, headers={"User-Agent": "folio-local/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            out.append((row["Date"], float(row["Close"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def coin_id_for(conn, ticker: str) -> str | None:
    """Resolve a CoinGecko coin id: the asset's name column, else KNOWN_COINS."""
    from .db import get_asset
    ticker = ticker.upper()
    row = get_asset(conn, ticker)
    if row and row["kind"] == "crypto" and row["name"]:
        return row["name"]
    return KNOWN_COINS.get(ticker)


def fetch_coingecko_history(coin_id: str, date: str) -> tuple[str, float] | None:
    """Close price (USD) of `coin_id` on `date` (YYYY-MM-DD) via the free
    CoinGecko history endpoint, or None on failure/no data."""
    import json
    y, m, d = date.split("-")
    url = COINGECKO_HISTORY_URL.format(coin_id=coin_id, dmy=f"{d}-{m}-{y}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "folio-local/0.4"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    try:
        return date, float(data["market_data"]["current_price"]["usd"])
    except (KeyError, TypeError, ValueError):
        return None


def backfill_crypto(conn, ticker: str, start: str, end: str) -> dict:
    """Store daily USD snapshots for a crypto ticker over [start, end] using
    the CoinGecko history endpoint (one request per day, free tier)."""
    import datetime as _dt
    coin_id = coin_id_for(conn, ticker)
    if not coin_id:
        return {"ticker": ticker.upper(), "start": start, "end": end, "stored": 0,
                "error": f"unknown CoinGecko coin id for {ticker.upper()}"}
    from .db import store_price
    stored = 0
    day = _dt.date.fromisoformat(start)
    end_d = _dt.date.fromisoformat(end)
    while day <= end_d:
        quote = fetch_coingecko_history(coin_id, day.isoformat())
        if quote:
            store_price(conn, ticker.upper(), quote[0], quote[1], "USD")
            stored += 1
        day += _dt.timedelta(days=1)
    return {"ticker": ticker.upper(), "start": start, "end": end, "stored": stored}


def backfill_prices(conn, ticker: str, start: str, end: str) -> dict:
    """Store daily snapshots for `ticker` over [start, end]: Stooq for
    stocks/ETFs, CoinGecko history for crypto (free, no key)."""
    import datetime as _dt
    _dt.date.fromisoformat(start)
    _dt.date.fromisoformat(end)
    from .db import MANUAL_KINDS, get_asset, store_price
    ticker = ticker.upper()
    row = get_asset(conn, ticker)
    if row and row["kind"] in MANUAL_KINDS:
        return {"ticker": ticker, "start": start, "end": end, "stored": 0,
                "error": f"{ticker} is a manual asset class "
                         f"({row['kind']}); store price snapshots yourself"}
    if (row and row["kind"] == "crypto") or (row is None and ticker in KNOWN_COINS):
        return backfill_crypto(conn, ticker, start, end)
    try:
        quotes = fetch_stooq_history(ticker.lower(), start, end)
    except OSError as e:
        return {"ticker": ticker, "start": start, "end": end,
                "stored": 0, "error": f"fetch failed: {e}"}
    for date, price in quotes:
        store_price(conn, ticker, date, price, "USD")
    return {"ticker": ticker, "start": start, "end": end,
            "stored": len(quotes)}
