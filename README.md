# folio-local

[![CI](https://github.com/bigpi/folio-local/actions/workflows/tests.yml/badge.svg)](https://github.com/bigpi/folio-local/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)

Самохостинговий трекер інвестиційного портфеля з **коректною** фінансовою
математикою (XIRR, TWR, мультивалютність). Python + FastAPI + SQLite.
Жодних хмар: усі дані живуть у вашому локальному SQLite-файлі.

## Чому це існує

Існуючі самохостингові трекери мають фундаментальні помилки в розрахунках:

> *«TWR показує мінус, хоч брокер показує +12% — щось не так з конвертацією
> валют»* — типова скарга користувачів Ghostfolio на r/selfhosted;
> відповідні issue висять відкритими понад рік. Доходність, порахована
> неправильно, — це не «косметика», а неправильні інвестиційні рішення.

- **Ghostfolio** — неправильні TWR/IRR при конвертації валют і для криптоактивів;
  відповідні issue висять відкритими понад рік (обговорення на r/selfhosted).
- **Portfolio Performance** — точна математика, але desktop-only (Java),
  без web-доступу й мобільного перегляду.

folio-local існує, щоб дати **правильну** математику (XIRR тільки на зовнішніх
потоках, TWR між датами потоків, конвертація за курсом на дату транзакції)
у простому self-hosted вебзастосунку — без Docker, без ключів API, без хмар.

## Швидкий старт

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload                   # http://127.0.0.1:8000
pytest                                              # математика під тестами
```

Вимоги: Python 3.12+. Без Docker, без ключів API, без хмар.

Автоматичний smoke-тест (запускає сервер на випадковому порті, перевіряє
головні ендпоінти, виводить PASS/FAIL):

```bash
bash scripts/smoke.sh
```

## Скріншоти

| Дашборд | Імпорт CSV |
|---|---|
| ![Дашборд: вартість, P/L, XIRR, графік](docs/screenshot-dashboard.png) | ![Візард мапінгу колонок CSV](docs/screenshot-import.png) |

> Плейсхолдери — додайте реальні скріншоти у `docs/` перед релізом.

## Можливості (v0.4.0)

- **Імпорт довільного брокерського CSV**: завантажте файл → попередній
  перегляд колонок → зіставте їх з полями (дата/тікер/дія/кількість/ціна/
  валюта) → імпорт. Підтримуються формати дати `YYYY-MM-DD`, `DD.MM.YYYY`,
  `MM/DD/YYYY`, `YYYYMMDD` та інші; нормалізація значень дій (`Buy`→`buy`).
- **Пресети брокерів**: IBKR (Trades) та Revolut — мапінг колонок і формат
  дати підставляються автоматично (`GET /api/import/presets`).
- **Позиції за рахунком**: тікер, кількість, середня ціна, поточна вартість, P/L.
- **Розподіл активів**: частки stock/ETF/crypto + кеш ( doughnut-діаграма).
- **Дивідендний календар**: отримані дивіденди за місяцями й тікерами,
  фільтр за роком.
- **Податковий прев'ю**: реалізовані прибутки за рік, метод FIFO/LIFO.
- **Backfill історії цін** за діапазон дат (Stooq для акцій, CoinGecko
  history для крипти).
- **Крипта в портфелі**: BTC/ETH/SOL та інші — ціни через CoinGecko (free,
  без ключа), уніфіковані з акціями в holdings та allocation.
- **Benchmark-лінія**: SPY (або будь-який Stooq-тікер) на графіку вартості,
  нормована на 100 — «а що якби просто купив індекс».
- **Tax report export**: CSV з реалізованими прибутками за рік (FIFO/LIFO)
  + друкована HTML-версія.
- **Панель попереджень**: buy/sell без ціни, пропуски FX-курсів, тікери без
  свіжих котирувань (`GET /api/warnings`).
- **UI**: темна тема, селектор періоду (1М/3М/6М/1Р/Всі), responsive
  таблиці.
- Портфель: вартість, P/L, XIRR, TWR, графік вартості (Chart.js).
- Ціни: Stooq (акції/ETF), CoinGecko (крипта). Курси: ECB (безкоштовний XML).

## Базові запити

```bash
# рахунок
curl -X POST localhost:8000/api/accounts -H 'content-type: application/json' \
  -d '{"name": "Main", "currency": "EUR"}'

# курси валют (одноразово або POST /api/fx/refresh для свіжих ECB-курсів)
curl -X POST localhost:8000/api/fx -H 'content-type: application/json' \
  -d '{"date": "2024-01-01", "rates": {"USD": 1.1}}'

# транзакції
curl -X POST localhost:8000/api/transactions -H 'content-type: application/json' \
  -d '{"account_id":1,"type":"deposit","date":"2024-01-01","amount":1000,"currency":"EUR"}'
curl -X POST localhost:8000/api/transactions -H 'content-type: application/json' \
  -d '{"account_id":1,"type":"buy","date":"2024-01-02","ticker":"AAPL","quantity":5,"price":190,"currency":"USD"}'

# оновити ціни (Stooq для акцій, CoinGecko для крипти)
curl -X POST localhost:8000/api/prices/update -H 'content-type: application/json' \
  -d '["AAPL", "MSFT"]'

# backfill історії цін за період
curl -X POST localhost:8000/api/prices/backfill -H 'content-type: application/json' \
  -d '{"ticker":"AAPL","start":"2024-01-01","end":"2024-06-30"}'

# портфель і позиції
curl localhost:8000/api/portfolio?account_id=1
curl localhost:8000/api/holdings?account_id=1

# імпорт: фіксовані колонки
curl -X POST localhost:8000/api/import/csv -H 'content-type: application/json' \
  -d '{"account_id":1,"csv_text":"date,ticker,action,quantity,price,currency\n2024-01-01,,deposit,,1000,EUR"}'

# імпорт: довільний CSV з мапінгом колонок
curl -X POST localhost:8000/api/import/mapped -H 'content-type: application/json' \
  -d '{"account_id":1,"csv_text":"TradeDate,Symbol,Side,Quantity,TradePrice,Currency\n20240115,AAPL,Buy,10,190.5,USD",
       "mapping":{"date":"TradeDate","ticker":"Symbol","action":"Side","quantity":"Quantity","price":"TradePrice","currency":"Currency"},
       "date_format":"YYYYMMDD","action_map":{"buy":"buy","sell":"sell"}}'
```

UI: відкрийте http://127.0.0.1:8000/ — дашборд (графік вартості, P/L, XIRR),
таблиця позицій, візард імпорту CSV, backfill цін. Без build-степу.

## Що саме "правильного" в математиці

1. **XIRR** — тільки зовнішні потоки (deposits від'ємні, withdrawals
   додатні, поточна вартість додатною сьогодні). Buy/sell/dividend — це
   внутрішній рух і **не** потрапляє у XIRR-вхід.
2. **TWR** — ланцюг підперіодів між датами зовнішніх потоків:
   `r_i = (V(t_i) - F_i) / V(t_{i-1})`, TWR = добуток(1 + r_i) − 1.
3. **Мультивалютність** — кожна транзакція конвертується в валюту рахунку
   за курсом ECB **на дату транзакції** (курси зберігаються з датою), а не
   за "сьогоднішнім" курсом — типова помилка, через яку ламається TWR.

## Roadmap

- [x] MVP: математика (XIRR/TWR/мультивалютність), API, фіксований CSV-імпорт, UI
- [x] Alpha v0.1.0: CSV column-mapping UI, holdings за рахунком, backfill цін
- [x] Брокерські пресети (IBKR, Revolut) для імпорту в один клік
- [x] Календар дивідендів (місяці/тікети, фільтр за роком)
- [x] Розподіл активів (asset allocation doughnut)
- [x] Податковий звіт FIFO/LIFO (попередній перегляд реалізованих прибутків)
- [x] v0.4.0: крипта через CoinGecko history, benchmark SPY, tax report export,
      панель попереджень, dark UI з селектором періоду
- [ ] Крипто-транзакції з блокчейн-експлорерів
- [ ] Класи активів: облігації, метали, нерухомість (ручна оцінка)
- [ ] Basic auth / багатокористувацький доступ
- [ ] Одношаговий деплой-скрипт (без Docker)

## Contributing

PRs and issues are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for
environment setup, test running, and commit style. Security issues: see
[SECURITY.md](SECURITY.md) (report privately, no public issues). The project
is Ukrainian + English only — it will never include Russian localization.

## Suggested GitHub topics

`portfolio-tracker` `self-hosted` `finance` `investments` `xirr` `twr`
`fastapi` `sqlite` `python` `pwa` `privacy-first` `fintech` `broker-import`
`dividends`

## Ліцензія

MIT (див. [LICENSE](LICENSE)). Джерела даних: Stooq (CSV, безкоштовно),
CoinGecko (free tier), курси валют — ECB (безкоштовний XML, без ключа).
