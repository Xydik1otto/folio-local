# folio-local

Самохостинговий трекер інвестиційного портфеля з **коректною** фінансовою
математикою (XIRR, TWR, мультивалютність). Python + FastAPI + SQLite.
Жодних хмар: усі дані живуть у вашому локальному SQLite-файлі.

## Проблема

Існуючі самохостингові трекери мають фундаментальні помилки в розрахунках:

- **Ghostfolio** — неправильні TWR/IRR при конвертації валют і для криптоактивів;
  відповідні issue висять відкритими понад рік (обговорення на r/selfhosted).
  Дохідність портфеля, порахована неправильно, — це не "косметика", а
  неправильні інвестиційні рішення.
- **Portfolio Performance** — точна математика, але desktop-only (Java),
  без web-доступу й мобільного перегляду.

## Evidence (розмір ніші)

- Ніша "finance" має **193 pay signals** на Market Gap Scanner — найвищий
  показник готовності платити серед досліджених ніш.
- 42% людей забувають про платні підписки (Capterra) — люди потребують
  контролю над своїми грошима локально, без віддачі даних третім сторонам.

## Швидкий старт

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload          # http://127.0.0.1:8000
pytest                                     # математика під тестами
```

### Базові запити

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

# портфель: вартість, P/L, XIRR
curl localhost:8000/api/portfolio?account_id=1

# імпорт CSV (фіксовані колонки: date,ticker,action,quantity,price,currency[,fees,name,kind])
curl -X POST localhost:8000/api/import/csv -H 'content-type: application/json' \
  -d '{"account_id":1,"csv_text":"date,ticker,action,quantity,price,currency\n2024-01-01,,deposit,,1000,EUR"}'
```

UI: відкрийте http://127.0.0.1:8000/ — мінімальна сторінка з Chart.js
(графік вартості портфеля, P/L, XIRR). Без build-степу.

## Що саме "правильного" в математиці

1. **XIRR** — тільки зовнішні потоки (deposits відʼємні, withdrawals
   додатні, поточна вартість додатною сьогодні). Buy/sell/dividend — це
   внутрішній рух і **не** потрапляє у XIRR-вхід.
2. **TWR** — ланцюг підперіодів між датами зовнішніх потоків:
   `r_i = (V(t_i) - F_i) / V(t_{i-1})`, TWR = добуток(1 + r_i) − 1.
3. **Мультивалютність** — кожна транзакція конвертується в валюту рахунку
   за курсом ECB **на дату транзакції** (курси зберігаються з датою), а не
   за "сьогоднішнім" курсом — типова помилка, через яку ламається TWR.

## Ліцензія

MIT. Дані цін: Stooq (CSV, безкоштовно), CoinGecko (free tier), курси валют:
ECB (безкоштовний XML, без ключа).
