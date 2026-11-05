# folio-local

[![CI](https://github.com/bigpi/folio-local/actions/workflows/tests.yml/badge.svg)](https://github.com/bigpi/folio-local/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)

Self-hosted investment portfolio tracker with **correct** financial math
(XIRR, TWR, multi-currency). Python + FastAPI + SQLite. No cloud: all data
lives in your local SQLite file. Ukrainian-language README:
[README.md](README.md).

## Why it exists

Existing self-hosted trackers get the math fundamentally wrong:

> *"TWR shows negative while my broker shows +12% — something is off with the
> currency conversion"* — a typical Ghostfolio complaint on r/selfhosted;
> the corresponding issues have stayed open for over a year. Returns computed
> incorrectly are not a cosmetic bug — they lead to wrong investment decisions.

- **Ghostfolio** — incorrect TWR/IRR on currency conversion and for crypto
  assets; related issues open for over a year (r/selfhosted threads).
- **Portfolio Performance** — correct math, but desktop-only (Java), no web
  access and no mobile view.

folio-local exists to give you **correct** math (XIRR on external flows only,
TWR chained between flow dates, conversion at the exchange rate of the
transaction date) in a simple self-hosted web app — no Docker, no API keys,
no cloud.

## Quick start

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload                   # http://127.0.0.1:8000
pytest                                              # the math is under tests
```

Requirements: Python 3.12+. No Docker, no API keys, no cloud. See
[INSTALL.md](INSTALL.md) for a step-by-step guide for non-programmers
(Windows `start.bat` + autostart, Linux systemd user unit).

Automated smoke test (starts the server on a random port, checks the main
endpoints, prints PASS/FAIL):

```bash
bash scripts/smoke.sh
```

## Screenshots

| Dashboard | CSV import |
|---|---|
| ![Dashboard: value, P/L, XIRR, chart](docs/screenshot-dashboard.png) | ![CSV column-mapping wizard](docs/screenshot-import.png) |

> Placeholders — add real screenshots to `docs/` before release.

## Features (v1.0.0)

- **Arbitrary broker CSV import**: upload a file → column preview → map them
  to fields (date/ticker/action/quantity/price/currency) → import. Date
  formats `YYYY-MM-DD`, `DD.MM.YYYY`, `DD-MM-YYYY`, `MM/DD/YYYY`,
  `YYYYMMDD` and more; action normalisation (`Buy`→`buy`).
- **Broker presets**: IBKR (Trades), Revolut, Trade Republic, DEGIRO,
  Fidelity, and a Tinkoff-format broker report (English column headers) —
  column mapping and date format pre-filled automatically
  (`GET /api/import/presets`).
- **Holdings per account**: ticker, quantity, average price, current value, P/L.
- **Asset allocation**: stock/ETF/crypto shares + cash (doughnut chart).
- **Dividend calendar**: dividends received by month and ticker, year filter.
- **Tax preview**: realised gains per year, FIFO/LIFO.
- **Price history backfill** over a date range (Stooq for stocks, CoinGecko
  history for crypto).
- **Crypto in the portfolio**: BTC/ETH/SOL and others — prices via CoinGecko
  (free, no key), unified with stocks in holdings and allocation.
- **Benchmark line**: SPY (or any Stooq ticker) on the value chart, normalised
  to 100 — "what if I had just bought the index".
- **Tax report export**: CSV with realised gains per year (FIFO/LIFO) plus a
  printable HTML version.
- **Warnings panel**: buy/sell without a price, FX-rate gaps, tickers without
  fresh quotes (`GET /api/warnings`).
- **Mobile PWA**: installable (web manifest + service worker), responsive UI,
  works offline after the first load.
- **Privacy-first**: no registration, no telemetry, no tracker cookies — the
  [«no-signup accounting» page](/privacy) explains what that means in
  practice (data never leaves your device).
- **One-click backup/restore**: download a snapshot of the whole SQLite
  database (`GET /api/backup`), restore it from a file (`POST /api/restore`,
  validated before it replaces the live DB).
- **One-click data export**: everything as JSON, transactions as CSV
  (`GET /api/export`).
- **UI**: dark theme, period selector (1M/3M/6M/1Y/All), responsive tables,
  UA/EN language switcher with browser-language detection.
- Portfolio: value, P/L, XIRR, TWR, value chart (Chart.js).
- Prices: Stooq (stocks/ETF), CoinGecko (crypto). FX rates: ECB (free XML).

## Basic requests

```bash
# account
curl -X POST localhost:8000/api/accounts -H 'content-type: application/json' \
  -d '{"name": "Main", "currency": "EUR"}'

# FX rates (once, or POST /api/fx/refresh for fresh ECB rates)
curl -X POST localhost:8000/api/fx -H 'content-type: application/json' \
  -d '{"date": "2024-01-01", "rates": {"USD": 1.1}}'

# transactions
curl -X POST localhost:8000/api/transactions -H 'content-type: application/json' \
  -d '{"account_id":1,"type":"deposit","date":"2024-01-01","amount":1000,"currency":"EUR"}'
curl -X POST localhost:8000/api/transactions -H 'content-type: application/json' \
  -d '{"account_id":1,"type":"buy","date":"2024-01-02","ticker":"AAPL","quantity":5,"price":190,"currency":"USD"}'

# update prices (Stooq for stocks, CoinGecko for crypto)
curl -X POST localhost:8000/api/prices/update -H 'content-type: application/json' \
  -d '["AAPL", "MSFT"]'

# price history backfill over a range
curl -X POST localhost:8000/api/prices/backfill -H 'content-type: application/json' \
  -d '{"ticker":"AAPL","start":"2024-01-01","end":"2024-06-30"}'

# portfolio and holdings
curl localhost:8000/api/portfolio?account_id=1
curl localhost:8000/api/holdings?account_id=1

# import: fixed columns
curl -X POST localhost:8000/api/import/csv -H 'content-type: application/json' \
  -d '{"account_id":1,"csv_text":"date,ticker,action,quantity,price,currency\n2024-01-01,,deposit,,1000,EUR"}'

# import: arbitrary CSV with column mapping
curl -X POST localhost:8000/api/import/mapped -H 'content-type: application/json' \
  -d '{"account_id":1,"csv_text":"TradeDate,Symbol,Side,Quantity,TradePrice,Currency\n20240115,AAPL,Buy,10,190.5,USD",
       "mapping":{"date":"TradeDate","ticker":"Symbol","action":"Side","quantity":"Quantity","price":"TradePrice","currency":"Currency"},
       "date_format":"YYYYMMDD","action_map":{"buy":"buy","sell":"sell"}}'
```

UI: open http://127.0.0.1:8000/ — dashboard (value chart, P/L, XIRR),
holdings table, CSV import wizard, price backfill. No build step.

## Authentication (optional)

By default the server is open on localhost only — enough for a single local
user. If you expose the portfolio through a reverse proxy, VPN or home network,
enable single-user Basic auth with two environment variables:

```bash
export FOLIO_AUTH_USER="alice"
export FOLIO_AUTH_PASSWORD="a-long-strong-password"
```

Every path except `/api/health` (kept open for uptime monitors) then answers
`401` without valid credentials. Only serve Basic auth over HTTPS — terminate
TLS on the reverse proxy (nginx, Caddy).

## What exactly is "correct" in the math

1. **XIRR** — external flows only (deposits negative, withdrawals positive,
   current value positive today). Buy/sell/dividend are internal movements
   and **do not** enter the XIRR input.
2. **TWR** — chained sub-period returns between external flow dates:
   `r_i = (V(t_i) - F_i) / V(t_{i-1})`, TWR = product(1 + r_i) − 1.
3. **Multi-currency** — every transaction is converted to the account
   currency at the ECB rate **on the transaction date** (rates are stored
   with their date), not at "today's" rate — the classic mistake that breaks
   TWR.

## Native core (optional): .NET 10 accelerator

The computationally critical math (XIRR Newton+bisection ACT/365, TWR,
normalized benchmark series) is duplicated in a C# library,
`dotnet/FolioCore` — an **exact** port of `backend/math_finance.py`: same
formulas, same defaults (`lo=-0.9999, hi=10, tol=1e-10`), same error
messages.

- `backend/native_accel.py` locates the compiled `FolioCli` CLI (first
  `$FOLIO_NATIVE`, then `dotnet/FolioCli/bin/Release/…/publish/`, then
  `dotnet <FolioCli.dll>`), hands it a **batch of operations** in one call
  (JSON on stdin → JSON on stdout) and returns the results.
- If the executable/dotnet is unavailable or the native call fails —
  **graceful fallback** to the pure-Python implementation; the app behaves
  exactly as before, just slower.
- The two implementations agree to a float tolerance of 1e-9, pinned by
  comparative tests (`tests/test_native_accel.py`).

Build (needs the .NET SDK 10; produces a ~70 MB self-contained exe, no
runtime required):

```bash
scripts/build_native.sh        # Windows: scripts\build_native.bat
```

Measured (Ryzen laptop, `python scripts/benchmark_native.py`, 3 runs):

| Scenario | Python | .NET core | speedup |
|---|---:|---:|---:|
| Single XIRR, 100,000 flows | 1522 ms | 519 ms | 2.9x |
| 2,000 XIRR ops in one native call | 258 ms | 189 ms | 1.4x |

The native core is an option, not a requirement: without it everything
runs on Python.

## Roadmap

- [x] MVP: math (XIRR/TWR/multi-currency), API, fixed CSV import, UI
- [x] Alpha v0.1.0: CSV column-mapping UI, per-account holdings, price backfill
- [x] Broker presets (IBKR, Revolut) for one-click import
- [x] Dividend calendar (months/tickers, year filter)
- [x] Asset allocation (doughnut chart)
- [x] Tax report FIFO/LIFO (realised-gains preview)
- [x] v0.4.0: crypto via CoinGecko history, SPY benchmark, tax export,
      warnings panel, dark UI with period selector
- [x] v1.0.0: Trade Republic / DEGIRO / Fidelity / Tinkoff-format presets,
      mobile PWA, privacy page, one-click backup/restore, data export,
      UA/EN UI switcher, demo data, INSTALL.md, packaging
- [x] Native computational core: C# .NET 10 port of XIRR/TWR/benchmark
      (`dotnet/FolioCore`) + subprocess accelerator with graceful fallback
- [ ] Crypto transactions from blockchain explorers
- [ ] Asset classes: bonds, metals, real estate (manual valuation)
- [ ] Basic auth / multi-user access
- [ ] One-step deploy script (no Docker)

## Contributing

PRs and issues are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Security issues: see [SECURITY.md](SECURITY.md) (report privately).

## Suggested GitHub topics

`portfolio-tracker` `self-hosted` `finance` `investments` `xirr` `twr`
`fastapi` `sqlite` `python` `pwa` `privacy-first` `fintech` `broker-import`
`dividends`

## License

MIT (see [LICENSE](LICENSE)). Data sources: Stooq (CSV, free), CoinGecko
(free tier), FX rates — ECB (free XML, no key).
