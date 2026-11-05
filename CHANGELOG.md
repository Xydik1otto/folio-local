# Changelog

Усі помітні зміни проєкту фіксуються тут.
Формат — [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
версонування — [Semantic Versioning](https://semver.org/lang/uk/).

## [0.4.0] — 2026-11-05

### Added
- **Крипта в портфелі**: денні ціни через CoinGecko history (free, без ключа)
  для тікерів типу BTC/ETH/SOL (`POST /api/prices/backfill` автоматично
  розпізнає крипто-тікери); авто-мапінг відомих тікерів на coin id;
  крипта уніфікована з акціями в holdings та allocation.
- **Benchmark-лінія**: `GET /api/portfolio/benchmark?symbol=spy` — вартість
  портфеля проти SPY (або будь-якого Stooq-тікера), обидві серії нормовані
  на 100 на першій спільній даті; перемикач «лінія SPY» на графіку.
- **Tax report export**: `GET /api/tax/export` — CSV-файл (реалізовані
  прибутки/збитки за рік, FIFO/LIFO) та друкована HTML-версія.
- **Панель попереджень**: `GET /api/warnings` — buy/sell без ціни, пропуски
  FX-курсів на дату транзакції, тікери без котирувань або з несвіжими
  котируваннями (> 30 днів); зведення угорі дашборда.
- **UI**: темна тема, селектор періоду (1М/3М/6М/1Р/Всі), responsive
  таблиці, вибір рахунка, кнопки експорту податкового звіту.
- `scripts/smoke.sh` — автоматичний smoke-тест: uvicorn на випадковому
  порті, curl-перевірки головних ендпоінтів, PASS/FAIL.
- CHANGELOG.md, FUNDING.yml (GitHub Sponsors), favicon + OG-мета теги.

## [0.3.0] — 2026-11-05

### Added
- Податковий прев'ю: реалізовані прибутки за рік, метод FIFO/LIFO
  (`GET /api/tax/preview`).
- Довільний брокерський CSV-імпорт з UI-мапінгом колонок і форматів дат.

## [0.2.0] — 2026-11-05

### Added
- Пресети брокерів IBKR та Revolut для імпорту в один клік
  (`GET /api/import/presets`, `POST /api/import/mapped`).
- Дивідендний календар: суми за місяцями й тікерами, фільтр за роком
  (`GET /api/dividends`).
- Розподіл активів: частки stock/ETF/crypto + кеш
  (`GET /api/portfolio/allocation`).

## [0.1.0-alpha] — 2026-11-05

### Added
- Ядро: XIRR (тільки зовнішні потоки), TWR (ланцюг підперіодів),
  мультивалютність за курсом ECB на дату транзакції.
- SQLite-сховище, REST API (FastAPI), фіксований CSV-імпорт, UI без
  build-степу, backfill цін через Stooq.

[0.4.0]: https://github.com/bigpi/folio-local/releases/tag/v0.4.0
[0.3.0]: https://github.com/bigpi/folio-local/releases/tag/v0.3.0
[0.2.0]: https://github.com/bigpi/folio-local/releases/tag/v0.2.0
[0.1.0-alpha]: https://github.com/bigpi/folio-local/releases/tag/v0.1.0-alpha
