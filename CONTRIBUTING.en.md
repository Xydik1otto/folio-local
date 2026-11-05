# Contributing to folio-local

> English version — primary mirror of [CONTRIBUTING.md](CONTRIBUTING.md) (Ukrainian).

## Project layout

The core is Python standard library + FastAPI; no heavy dependencies.

**`backend/` — server logic:**

| Module | Responsibility |
|---|---|
| `db.py` | SQLite schema (`accounts`, `assets`, `transactions`) and connections; plain `sqlite3`, no ORM |
| `math_finance.py` | Financial math: XIRR (Newton + bisection), TWR (time-weighted return), annualised figures |
| `native_accel.py` | Optional accelerator: runs the C# core (`dotnet/FolioCore`) as a subprocess; if it's absent — **graceful fallback** to pure Python, never crashes |
| `prices.py` | Price history: Stooq (stocks/ETFs), CoinGecko (crypto) |
| `fx.py` | Currency rates: daily ECB reference rates |
| `csv_import.py` | CSV parsing, column mapping, `DATE_FORMATS`, broker presets (`PRESETS`) |
| `portfolio.py` | Holdings, asset allocation, aggregates |
| `report.py` | FIFO/LIFO tax report |
| `warnings.py` | Warnings panel (portfolio state) |
| `backup.py`, `demo.py`, `main.py` | Backup/restore, demo data, FastAPI app |

**`static/` — UI:** `index.html` (vanilla JS, no frameworks), `i18n/uk.json` +
`i18n/en.json` (identical key sets), `sw.js` (PWA).

**`dotnet/FolioCore`** — native C# core (XIRR/TWR/benchmark); binaries are
built by `scripts/build_native.sh` / `build_native.bat`; without it everything
runs on Python. **`tests/`** — 172+ tests, fast and network-free.

## Environment & tests

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
pytest -q                          # full suite (172+), fast, offline
pytest tests/test_xirr.py -q       # one file
bash scripts/smoke.sh              # smoke test against a live server
```

Tests must not require internet. Every feature/fix comes with a test.

## Adding a broker preset

A preset is a one-click import template: columns the UI pre-selects when they
match the uploaded file. Step by step:

1. **Study the broker's export format**: exact column headers (case matters),
   the date format (`YYYYMMDD`, `YYYY-MM-DD`, `DD.MM.YYYY`, `MM/DD/YYYY`,
   `DD-MM-YYYY` — see `DATE_FORMATS` in `backend/csv_import.py`), how actions
   are spelled (`buy`/`kauf`/`Bought`…), where fees live.
2. **Add the preset to `PRESETS`** in `backend/csv_import.py`:
   ```python
   "my_broker": {
       "label": "My Broker — Trades export (Date/Symbol/…)",
       "mapping": {"date": "Date", "ticker": "Symbol", "action": "Side",
                   "quantity": "Quantity", "price": "Price",
                   "currency": "Currency", "fees": "Commission"},
       "date_format": "DD.MM.YYYY",   # or None if dates are already ISO
       "action_map": {"buy": "buy", "sell": "sell", "dividend": "dividend"},
   },
   ```
   Required mapping fields: `date, ticker, action, quantity, price, currency`.
3. **UI — nothing to do**: the `#presetSel` dropdown in `static/index.html`
   is populated dynamically from `GET /api/import/presets`; a new preset
   appears automatically.
4. **Tests** (`tests/test_presets.py`):
   - `test_every_preset_is_well_formed` validates structure automatically;
   - add a CSV fixture with the broker's **real headers** and an end-to-end
     test via `import_with_preset(conn, 1, CSV, "my_broker")` — check
     transaction types, date normalisation and currency;
   - if the preset is part of the promised set, add its name to the set in
     `test_new_preset_names_present`.
5. `pytest tests/test_presets.py -q` green, then the full suite.

## Adding an asset class

Today `assets.kind` is a CHECK constraint in the SQLite schema (`stock`,
`etf`, `crypto`, `cash`). A new class (say, bonds) touches several places:

1. **Schema**: extend the CHECK in `CREATE TABLE assets` in `backend/db.py` +
   a migration for existing DBs (SQLite can't ALTER CONSTRAINT — the standard
   recipe: new table → copy → rename).
2. **Logic**: how is the class valued? If it needs price history — a data
   source in `backend/prices.py` (privacy-respecting: no keys, no accounts);
   if manual valuation — make sure `portfolio.py` aggregates `kind` groups
   correctly and doesn't break on missing prices.
3. **UI**: the allocation doughnut and tables take `kind` from the API —
   add translations to `static/i18n/uk.json` **and** `en.json` if needed
   (key sets must match; this is test-enforced).
4. **Tests**: Python-vs-native parity (`tests/test_native_accel.py`),
   aggregates (`tests/test_allocation.py`), edge cases (zero quantities,
   missing prices).

If a change touches the financial math (XIRR/TWR), discuss it in an issue
first: the math here is deliberate and documented in the README.

## Proposing a feature

1. Open an issue with the **Feature request** template — describe the problem
   you're solving, not just the solution.
2. For financial-math changes (XIRR/TWR/FX) — discuss first.
3. PRs: small, with a test, green `pytest`. No new mandatory dependencies
   (standard library > new library).

## Branches

- **`master`** — the stable line: web app + C# core. All backend, UI, test
  and documentation changes land here.
- **`mobile/android-ios`** — the mobile port (Capacitor 6: Android + iOS
  shell, CI APK/IPA builds). Mobile changes are NOT merged into master
  automatically; if you touch shared files, reconcile both branches.

## Commit style

- Format: `Area: short description` — e.g. `Presets: Fidelity dividend rows`,
  `UI: fix chart resize`, `Docs: native-core architecture`.
- One logical change = one commit. A test for every feature/fix.
- Ukrainian or English description is fine; no machine-translated filler.

## Languages & i18n

- UI and docs are **Ukrainian and English**. Dictionaries:
  `static/i18n/uk.json` + `static/i18n/en.json`, identical key sets
  (test-enforced). Default: browser language with UA fallback.
- **Never add a Russian locale** — the project owner's political decision.
  Not in the UI, not in presets, not in docs. Ever.
- User-visible text is never hardcoded in logic — it goes through the
  dictionaries.

## Non-negotiable rules

- No telemetry, trackers or analytics — this is a privacy-first project.
- User data never leaves their device/server — don't add anything that
  ships it elsewhere.
- No absolute paths, tokens or personal data in code.
- Optional components (the native core) never become mandatory: without them
  everything runs on pure Python.
