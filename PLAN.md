# PLAN — folio-local

Самохостинговий трекер інвестиційного портфеля з коректною фінансовою
математикою. Локальні дані (SQLite), безкоштовні джерела ринкових даних.

## 1. Цільова аудиторія

- **Первинна:** DIY-інвестори (дохід $60k+), які самостійно тримають портфель
  з акцій/ETF/крипти в 2+ валютах і не довіряють рообро-адvisors. Вже
  самохостять щось (Home Assistant, Nextcloud, Vaultwarden).
- **Вторинна:** експати та українці з рахунками в UAН + EUR/USD — для них
  мультивалютність не "опція", а щоденна реальність; існуючі інструменти
  ламаються саме на конвертації.
- **Третинна:** маленькі сімейні офіси (2–5 рахунків, спільний перегляд).

Чому ця ніша: **193 pay signals** у категорії finance — найвища готовність
платити з усіх досліджених ніш. Аудиторія технічно грамотна, розуміє цінність
коректної математики і вміє запустити Docker-контейнер.

## 2. Проблема / Evidence

- Ghostfolio: фундаментальні помилки TWR/IRR при валютних конвертаціях та
  крипті; issue відкритий 1+ рік (r/selfhosted). Альтернативи закриті або
  теж з помилками.
- Portfolio Performance: правильна математика, але desktop-only (Java),
  немає web/mobile — не підходить для "заглянути з телефона".
- 42% людей забувають про платні підписки (Capterra); $17/міс витрачається
  на невикористані підписки (CNET 2025) — приватні фінанси потребують
  простого локального інструменту без віддачі банківських даних хмарі.

## 3. MVP scope (реалізовано)

- Python FastAPI + SQLite (stdlib sqlite3, без ORM).
- Моделі: Account, Asset, Transaction (buy/sell/dividend/fee/deposit/
  withdrawal), PriceSnapshot, FxRate.
- Математика (`backend/math_finance.py`, `backend/portfolio.py`):
  - XIRR: Newton-Raphson + bisection fallback, ACT/365;
  - TWR: ланцюг підперіодів між зовнішніми потоками;
  - мультивалютна вартість: конвертація за курсом на дату транзакції.
- Ціни: Stooq CSV (акції/ETF), CoinGecko (крипта). Курси: ECB daily XML.
- CSV-імпорт з фіксованими колонками `date,ticker,action,quantity,price,
  currency[,fees,name,kind]`.
- REST API: `/api/accounts`, `/api/transactions`, `/api/prices*`, `/api/fx*`,
  `/api/portfolio` (value/P/L/XIRR), `/api/portfolio/history`, `/api/portfolio/twr`.
- Frontend: один `static/index.html` з Chart.js з CDN, без build-степу.
- Тести: pytest на XIRR (закриті форми), TWR (штучні транзакції),
  валютну конвертацію, CSV-валідацію, end-to-end через TestClient.

## 4. Архітектура

```
backend/
  db.py            sqlite3-схема: accounts, assets, transactions,
                   price_snapshots, fx_rates
  math_finance.py  чисті функції: npv, xirr, twr (без I/O)
  fx.py            ECB XML -> fx_rates; convert(amount, src, dst, rates)
  prices.py        Stooq CSV + CoinGecko -> price_snapshots
  csv_import.py    фіксований мапер колонок -> transactions
  portfolio.py     ledger-реплей -> вартість/P/L/XIRR/TWR
  main.py          FastAPI (REST + static)
static/index.html  Chart.js, fetch до /api/*
```

Ключові інваріанти (те, що ламано в конкурентів):

1. Кожна сума зберігається у своїй валюті + конвертується в валюту рахунку
   курсом **на дату транзакції** (fx_rates має дату).
2. XIRR-вхід = тільки deposits/withdrawals/final value.
3. TWR-межі = тільки дати зовнішніх потоків.

## 5. Roadmap

### MVP (поточний коміт)
Математика + API + CSV-імпорт + односторінковий UI + тести.

### v1 — "щоденний драйвер"
- Column-mapping UI для довільних CSV (брокерські експорти).
- Історія цін:/backfill через Stooq діапазонами; парсинг крипто-транзакцій
  з блокчейн-експлорерів.
- Asset класи: bonds, metals, real estate (ручна оцінка).
- Docker + docker-compose; бекапи SQLite (litestream).
- Авторизація (single-user basic auth + HTTPS через reverse proxy).

### v1.5 — "правильна аналітика глибше"
- MWR vs TWR поруч, rolling returns, drawdown, allocation drift.
- Податкові репорти: FIFO/LIFO lots, дивіденди по країнах.
- Мобільний PWA (той самий FastAPI + сервіс-воркер).

### v2 — "спільний продукт"
- Multi-user з запрошеннями (сімейний офіс).
- Планові API: IBKR Flex, Degiro, Binance (read-only ключі, зберігання
  локально).
- Плагінна система імпортерів.

## 6. Монетизація (freemium self-hosted / one-time)

- **Core — назавжди безкоштовний** (self-hosted, MIT): математика, CSV,
  1 користувач.
- **Pro — one-time $49** (ліцензійний ключ, без хмарних сервісів):
  податкові репорти (FIFO/LIFO), плагіни брокерських імпортів, priority support.
- **Family pack — one-time $79:** multi-user, спільні портфелі.
- Опційний "managed" хостинг $5/міс для нетехнічних — тільки якщо буде
  органічний попит (анонси на r/selfhosted; не розвивати до v1.5).

## 7. Ризики

| Ризик | Імовірність | Мітигація |
|---|---|---|
| Stooq змінить формат/закриє доступ | середня | абстракція `PriceProvider`, запасні джерела (Yahoo, Alpha Vantage free) |
| Помилки в математиці, як у Ghostfolio | низька (тести) | властивості XIRR/TWR перевіряються на закритих формах; property-based тести в v1 |
| Довгі діапазони історії цін безкоштовно не покриваються | середня | ручні price snapshots + імпорт з CSV як fallback |
| SQLite + одночасний доступ | низька | WAL, single-user цільовий сценарій |
| Юридичні питання "не фінансова порада" | низька | дисклеймер, без сигналів/рекомендацій |

## 8. Free-tier джерела даних

| Джерело | Що | Ліміти |
|---|---|---|
| Stooq CSV `stooq.com/q/d/l` | щоденні OHLCV по акціях/ETF | безкоштовно, без ключа |
| CoinGecko `/simple/price` | крипта | 30 req/min free, без ключа |
| ECB `eurofxref-daily.xml` | курси валют vs EUR | щоденний XML, без ключа |
| Twelve Data (опційно) | додаткові біржі | 800 req/day free, ключ опційний |
