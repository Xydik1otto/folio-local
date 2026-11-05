# Import on-chain crypto transactions from a public blockchain explorer.
# Provider: blockchain.info /rawaddr (free, no API key; BTC).
# The parser is a PURE function of the explorer payload — network I/O lives
# only in fetch_rawaddr, so tests run offline on canned payloads.
#
# Mapping to folio-local transactions (portfolio semantics):
#   * coins received by the address  -> type "buy"   (position grows)
#   * coins sent out (net of change) -> type "sell"  (position shrinks)
#   * miner fee of an outgoing tx    -> type "fee"   (separate cash-cost line)
#   * self-transfer (net result 0)   -> skipped
#   * price stays None: on-chain transfers are not market trades; valuations
#     come from price snapshots (CoinGecko backfill), never guessed here.
from __future__ import annotations

import datetime as dt
import json
import urllib.parse
import urllib.request

RAWADDR_URL = "https://blockchain.info/rawaddr/{address}?cors=true"
SATOSHIS = 100_000_000  # BTC

# Base58 alphabet (Bitcoin addresses), used only as a sanity filter.
_BASE58_CHARS = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


class ExplorerError(ValueError):
    pass


def validate_address(address: str) -> str:
    address = (address or "").strip()
    if not (26 <= len(address) <= 62) or not set(address) <= _BASE58_CHARS:
        raise ExplorerError(f"not a valid base58 address: {address!r}")
    return address


def fetch_rawaddr(address: str, base_url: str = "https://blockchain.info") -> dict:
    """GET /rawaddr/<address> and decode the JSON payload. Raises ExplorerError
    on network or parse failure (caller decides how to surface it)."""
    address = validate_address(address)
    url = RAWADDR_URL.format(address=urllib.parse.quote(address))
    if base_url:
        url = f"{base_url.rstrip('/')}/rawaddr/{urllib.parse.quote(address)}?cors=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "folio-local/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except OSError as e:
        raise ExplorerError(f"explorer request failed: {e}") from e
    except (ValueError, UnicodeDecodeError) as e:
        raise ExplorerError(f"explorer returned invalid JSON: {e}") from e
    if not isinstance(data, dict) or "txs" not in data:
        raise ExplorerError("unexpected rawaddr payload: missing 'txs'")
    return data


def transactions_from_payload(payload: dict, address: str,
                              ticker: str = "BTC") -> list[dict]:
    """Pure parser: rawaddr payload -> folio-local transaction dicts
    (oldest first, ready for INSERT)."""
    address = validate_address(address)
    if not isinstance(payload, dict) or not isinstance(payload.get("txs"), list):
        raise ExplorerError("payload must be a rawaddr object with a 'txs' list")
    ticker = ticker.upper()
    out: list[dict] = []
    for tx in payload["txs"]:
        if not isinstance(tx, dict):
            raise ExplorerError("txs entries must be objects")
        try:
            result_sats = int(tx["result"])       # net satoshis to the address
            epoch = int(tx["time"])
        except (KeyError, TypeError, ValueError) as e:
            raise ExplorerError(f"tx missing result/time: {e}") from e
        if result_sats == 0:
            continue  # internal shuffle / self-transfer: nothing to record
        date = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).date().isoformat()
        txhash = str(tx.get("hash", ""))[:16]
        if result_sats > 0:
            out.append({
                "type": "buy", "date": date, "ticker": ticker,
                "quantity": result_sats / SATOSHIS, "price": None,
                "amount": None, "fees": 0.0, "currency": ticker,
                "note": f"on-chain receive {txhash}",
            })
        else:
            fee_sats = int(tx.get("fee") or 0)
            sent_sats = -result_sats - fee_sats  # what actually left the wallet
            if sent_sats > 0:
                out.append({
                    "type": "sell", "date": date, "ticker": ticker,
                    "quantity": sent_sats / SATOSHIS, "price": None,
                    "amount": None, "fees": 0.0, "currency": ticker,
                    "note": f"on-chain send {txhash}",
                })
            if fee_sats > 0:
                out.append({
                    "type": "fee", "date": date, "ticker": ticker,
                    "quantity": None, "price": None,
                    "amount": fee_sats / SATOSHIS, "fees": 0.0,
                    "currency": ticker, "note": f"miner fee {txhash}",
                })
    return out


def fetch_and_parse(address: str, ticker: str = "BTC",
                    base_url: str = "https://blockchain.info") -> list[dict]:
    """Convenience: fetch + parse in one call (used by the API endpoint)."""
    return transactions_from_payload(fetch_rawaddr(address, base_url),
                                     address, ticker)
