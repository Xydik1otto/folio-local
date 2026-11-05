# Changelog

Усі помітні зміни проєкту фіксуються тут.
Формат — [Keep a Changelog](https://keepachangelog.com/uk/1.1.0/),
версонування — [Semantic Versioning](https://semver.org/lang/uk/).

## [Unreleased]

### Added
- **Нативне обчислювальне ядро (.NET 10, опціонально)**: `dotnet/FolioCore` —
  точний порт `backend/math_finance.py` на C# (XIRR Newton+bisection ACT/365,
  TWR, нормований benchmark-ряд; ті самі формули, значення за замовчуванням
  і тексти помилок) + CLI-драйвер `FolioCli` (JSON на stdin → JSON на stdout,
  пакет операцій одним викликом, single-file publish). Збірка —
  `scripts/build_native.sh` / `.bat`.
- **Subprocess-акселератор** `backend/native_accel.py`: знаходить exe
  (`FOLIO_NATIVE` → `dotnet/FolioCli/bin/Release/…/publish/` → `dotnet` з
  DLL), передає йому роботу пакетом; якщо exe/dotnet недоступний або впав —
  graceful fallback на чисту Python-реалізацію. Результати двох реалізацій
  ідентичні (float tolerance 1e-9) — закріплено порівняльними тестами
  на edge-кейсах (від'ємні потоки, один потік, від'ємна дохідність,
  відсутній/зламаний exe).

### Changed
- `portfolio_xirr`/`twr_series` тепер рахуються через `native_accel`
  (нативно, коли ядро зібрано; інакше — як раніше, на Python).
- `math_finance` отримав чисту функцію `normalized_benchmark` (нормований
  benchmark-ряд без HTTP-обгортки).
- У README (UA+EN) — розділ про нативне ядро з замірами: один XIRR на
  100 000 потоків — 2.9x проти Python; 2 000 XIRR-операцій одним
  native-викликом — 1.4x. Заміряється скриптом
  `scripts/benchmark_native.py`.

## [1.0.0] — 2026-11-05

«Готово для чужих користувачів»: сторонній користувач запускає проєкт за
5 хвилин без знання коду.

### Added
- **Пресети ще 4 брокерів**: Trade Republic, DEGIRO, Fidelity і
  Tinkoff-загальний формат CSV (англомовні заголовки; російської локалізації
  в проєкті НЕМАЄ і не буде — політичне рішення власника). Разом з IBKR,
  Revolut і generic — 7 пресетів (`GET /api/import/presets`). Новий формат
  дати `DD-MM-YYYY`.
- **Mobile PWA**: `static/manifest.webmanifest` (installable, standalone) +
  service worker `static/sw.js` (офлайн-шелл: cache-first для статики,
  API ніколи не кешується), мобільна responsive-верстка, шрифт ≥ 16px
  на мобільних (без iOS-зуму).
- **Сторінка «Облік без реєстрації»** (`/privacy`): privacy-first пояснення —
  без реєстрації, без телеметрії, дані не залишають пристрій; без трекерів.
- **Backup/restore БД одним кліком**: `GET /api/backup` (консистентний
  snapshot через SQLite backup API) + `POST /api/restore` (валідація файлу
  перед заміною живої бази; support попередження в UI).
- **Експорт даних одним кліком**: `GET /api/export` — JSON (усі дані
  рахунку: транзакції, активи, ціни, FX) або CSV у канонічному форматі,
  який знову імпортується власним імпортером (круговий тест).
- **First-run demo data**: кнопка «Завантажити демо-дані» (`POST
  /api/demo-data`) — рахунок «Demo» з 10 транзакціями (акції, ETF, крипта,
  дивіденди, депозити), idempotent (409 при повторі).
- **i18n UA/EN перемикач у UI**: JSON-словники `static/i18n/{uk,en}.json`,
  авто-детект мови браузера, збереження вибору в localStorage. Російської
  локалізації не існує (і не з'явиться).
- **README.en.md** — англійська версія README для міжнародної аудиторії.
- **INSTALL.md** — покрокова інструкція для не-програміста: Windows
  (`start.bat` — venv + залежності + сервер + браузер; автозапуск через
  папку Startup), Linux (`start.sh`, systemd user unit
  `scripts/folio-local.service`, enable-linger), оновлення, часті проблеми.
- **Packaging**: `pyproject.toml` (v1.0.0 metadata, console-script
  `folio-local`), перевірено `pip install -e .` у свіжому venv.
- **OSS hygiene** (репозиторій піде в опенсорс): CONTRIBUTING.md,
  SECURITY.md (приватне репортування вразливостей), issue-шаблони
  (укр+англ в одному файлі), скан на витоки приватності (жодних абсолютних
  шляхів/токенів — закріплено тестом), `.gitignore` покриває `.env`,
  секція Contributing + рекомендовані GitHub topics в обох README.
- **A11y**: aria-labels на всіх інтерактивних елементах, aria-live для
  повідомлень, видимий фокус (`:focus-visible`).

### Changed
- Версія API піднята до 1.0.0.

### Testing
- 96 → 150 тестів (7 нових тест-файлів), уся математика й нові фічі під
  тестами; тести не вимагають інтернету.

[1.0.0]: https://github.com/bigpi/folio-local/releases/tag/v1.0.0

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
