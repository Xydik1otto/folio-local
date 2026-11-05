# Contributing to folio-local / Як долучитися

> Українська версія — основна. Англійське дзеркало: [CONTRIBUTING.en.md](CONTRIBUTING.en.md).
> The English mirror lives in [CONTRIBUTING.en.md](CONTRIBUTING.en.md).

## Архітектура проєкту / Project layout

Все ядро — стандартна бібліотека Python + FastAPI; жодних тяжких залежностей.

**`backend/` — логіка сервера:**

| Модуль | Відповідає за |
|---|---|
| `db.py` | SQLite-схема (`accounts`, `assets`, `transactions`) і з'єднання; без ORM, чистий `sqlite3` |
| `math_finance.py` | Фінансова математика: XIRR (метод Ньютона + бісекція), TWR (time-weighted return), річні показники |
| `native_accel.py` | Опціональний акселератор: запускає C#-ядро (`dotnet/FolioCore`) як subprocess; якщо його немає — **graceful fallback** на чистий Python, ніколи не падає |
| `prices.py` | Історія цін: Stooq (акції/ETF), CoinGecko (крипта) |
| `fx.py` | Валютні курси: щоденні довідкові курси ЄЦБ (ECB) |
| `csv_import.py` | Парсинг CSV, мапінг колонок, `DATE_FORMATS` і пресети брокерів (`PRESETS`) |
| `portfolio.py` | Holdings, розподіл активів, агрегати |
| `report.py` | Податковий звіт FIFO/LIFO |
| `warnings.py` | Панель попереджень (стан портфеля) |
| `backup.py`, `demo.py`, `main.py` | Бекап/рестор, демо-дані, FastAPI-додаток |

**`static/` — UI:** `index.html` (vanilla JS, без фреймворків), `i18n/uk.json` +
`i18n/en.json` (однаковий набір ключів), `sw.js` (PWA).

**`dotnet/FolioCore`** — нативне C#-ядро (XIRR/TWR/benchmark), бінарник будують
`scripts/build_native.sh` / `build_native.bat`; без нього все працює на Python.
**`tests/`** — 172+ тести, швидко і без мережі.

## Середовище та тести / Environment & tests

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
pytest -q                          # весь набір (172+), швидко, без мережі
pytest tests/test_xirr.py -q       # один файл
bash scripts/smoke.sh              # смоук-тест живого сервера
```

Тести не мають вимагати інтернету. Кожна фіча/фікса — з тестом.

## Як додати брокерський пресет / Adding a broker preset

Пресет — шаблон імпорту «в один клік»: колонки, які UI заздалегідь підставить,
якщо вони збігаються з завантаженим файлом. Покроково:

1. **Вивчіть формат експорту брокера**: заголовки колонок (точно, з регістром),
   формат дати (`YYYYMMDD`, `YYYY-MM-DD`, `DD.MM.YYYY`, `MM/DD/YYYY`,
   `DD-MM-YYYY` — див. `DATE_FORMATS` у `backend/csv_import.py`), як записані
   дії (`buy`/`kauf`/`Bought`…), де зберігаються комісії.
2. **Додайте пресет у `PRESETS`** у `backend/csv_import.py`:
   ```python
   "my_broker": {
       "label": "My Broker — Trades export (Date/Symbol/…)",  # людиною, UA або EN
       "mapping": {"date": "Date", "ticker": "Symbol", "action": "Side",
                   "quantity": "Quantity", "price": "Price",
                   "currency": "Currency", "fees": "Commission"},
       "date_format": "DD.MM.YYYY",   # або None, якщо дата вже ISO
       "action_map": {"buy": "buy", "sell": "sell", "dividend": "dividend"},
   },
   ```
   Обов'язкові поля мапінгу: `date, ticker, action, quantity, price, currency`.
3. **UI — нічого не треба**: дропдаун `#presetSel` у `static/index.html`
   заповнюється динамічно з `GET /api/import/presets`, новий пресет з'явиться сам.
4. **Тести** (`tests/test_presets.py`):
   - `test_every_preset_is_well_formed` перевірить структуру автоматично;
   - додайте CSV-фікстуру з **реальними заголовками** брокера та
     end-to-end тест через `import_with_preset(conn, 1, CSV, "my_broker")` —
     перевірте типи транзакцій, нормалізацію дат і валюту;
   - якщо пресет — частина обіцяного набору, додайте його ім'я до множини
     в `test_new_preset_names_present`.
5. `pytest tests/test_presets.py -q` — зелений, потім весь набір.

## Як додати клас активу / Adding an asset class

Сьогодні `assets.kind` — CHECK-обмеження в SQLite-схемі (`stock`, `etf`,
`crypto`, `cash`). Новий клас (наприклад, облігації) торкається кількох місць:

1. **Схема**: розширте CHECK у `CREATE TABLE assets` у `backend/db.py` +
   міграція для існуючих БД (SQLite не вміє ALTER CONSTRAINT — стандартний
   прийом: нова таблиця → копіювання → перейменування).
2. **Логіка**: як клас оцінюється? Якщо потрібна історія цін — джерело даних
   у `backend/prices.py` (з повагою до privacy: без ключів, без акаунтів);
   якщо ручна оцінка — переконайтеся, що `portfolio.py` коректно агрегує
   `kind`-групи й не ламається на відсутніх цінах.
3. **UI**: розподіл активів (doughnut) і таблиці беруть `kind` з API —
   за потреби додайте переклади в `static/i18n/uk.json` **і** `en.json`
   (набори ключів мають збігатися, це перевіряється тестом).
4. **Тести**: паритет Python- і native-шляхів (`tests/test_native_accel.py`),
   агрегати (`tests/test_allocation.py`), крайні випадки (нульові кількості,
   відсутні ціни).

Якщо зміна торкається фінансової математики (XIRR/TWR) — спершу обговорення
в issue: математика тут свідома і задокументована в README.

## Як запропонувати фічу / Proposing a feature

1. Відкрийте issue з шаблоном **Feature request** — опишіть проблему, яку
   ви вирішуєте, а не тільки рішення.
2. Для змін у фінансовій математиці (XIRR/TWR/FX) — спершу обговорення.
3. PR: маленькі, з тестом, зелений `pytest`. Без нових обов'язкових
   залежностей (стандартна бібліотека > нова бібліотека).

## Гілки / Branches

- **`master`** — стабільна лінія: вебзастосунок + C#-ядро. Сюди йдуть усі
  зміни бекенду, UI, тестів, документації.
- **`mobile/android-ios`** — мобільний порт (Capacitor 6: Android + iOS
  оболонка, CI-збірки APK/IPA). Мобільні зміни НЕ зливаються в master
  автоматично; якщо змінюєте спільні файли — узгодьте обидві гілки.

## Стиль комітів / Commit style

- Формат: `Зона: короткий опис` — наприклад
  `Presets: Fidelity dividend rows`, `UI: fix chart resize`,
  `Docs: native-core architecture`.
- Одна логічна зміна = один commit. Тест на кожну фічу/фіксу.
- Опис українською або англійською, без машинно-перекладеного наповнювача.

## Мови та i18n / Languages & i18n

- UI і документація — **українська та англійська**. Словники:
  `static/i18n/uk.json` + `static/i18n/en.json`, однакові набори ключів
  (перевіряється тестом). Дефолт — мова браузера з fallback на UA.
- **Ніколи не додавати російську локалізацію** — політичне рішення власника
  проєкту. Не в UI, не в пресетах, не в документах. Ever.
- Текст, який бачить користувач, не хардкодиться в логіці — йде через словник.

## Правила, які не обговорюються / Non-negotiable rules

- **Ніколи не додавати російську локалізацію** (політичне рішення власника
  проєкту). UA/EN only. Ever.
- Жодних телеметрії, трекерів, аналітики — це privacy-first проєкт.
- Жодних абсолютних шляхів, токенів чи персональних даних у коді.
- Дані користувача не залишають його пристрій/сервер — не додавайте нічого,
  що надсилає їх кудись.
- Опціональні компоненти (нативне ядро) не стають обов'язковими: без них
  все працює на чистому Python.
