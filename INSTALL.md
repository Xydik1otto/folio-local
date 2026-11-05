# Встановлення folio-local — покроково, для не-програміста

folio-local — це програма, яка працює **на вашому комп'ютері**. Ніяких акаунтів,
хмар чи передавання даних. Все, що потрібно — встановити Python і запустити
один файл. Нижче — інструкції для Windows та Linux, налаштування автозапуску
та оновлення.

> English summary at the bottom of each section. Повна англійська версія —
> в кінці файлу (Quick start EN).

---

## Що вам знадобиться

1. **Python 3.12 або новіший** — безкоштовно з [python.org](https://www.python.org/downloads/).
   - Windows: під час встановлення обов'язково поставте галочку
     **«Add python.exe to PATH»**.
2. 10 хвилин часу. Все.

---

## Windows

### Крок 1. Завантажте проєкт

```bat
git clone https://github.com/bigpi/folio-local.git
cd folio-local
```

(Немає git? Натисніть на GitHub зелений кнопок **Code → Download ZIP**,
розпакуйте та відкрийте папку в Провіднику, потім відкрийте термінал у цій
папці: адресний рядок Провідника → наберіть `cmd` → Enter.)

### Крок 2. Натисніть `start.bat`

У папці проєкту **двічі клацніть `start.bat`** (або запустіть його з терміналу).
Скрипт сам:

1. створить віртуальне середовище `.venv` (при першому запуску),
2. встановить залежності (при першому запуску),
3. запустить сервер на `http://127.0.0.1:8000` і відкриє браузер.

Готово — дашборд відкрито. Далі натисніть **«Завантажити демо-дані»**,
щоб подивитися, як усе виглядає, або імпортуйте свій broker CSV.

> Що робить `start.bat` (для перевірки): `python -m venv .venv`,
> `.venv\Scripts\pip install -r requirements.txt`,
> `.venv\Scripts\uvicorn backend.main:app --port 8000`, старт браузера.

### Крок 3 (опційно). Автозапуск із Windows

Щоб folio-local стартував при вході в систему:

1. Натисніть `Win + R`, наберіть `shell:startup`, Enter.
2. У папку, що відкрилася, **скопіюйте ярлик** на `start.bat`
   (ПКМ по `start.bat` → «Надіслати» → «Робочий стіл (створити ярлик)»,
   потім перемістіть ярлик звідти у папку Startup) — або створіть там файл
   `folio-local.bat` з одним рядком:

```bat
"C:\шлях\до\folio-local\start.bat"
```

Тепер після кожного входу в Windows трекер доступний на
`http://127.0.0.1:8000`.

---

## Linux (Ubuntu/Debian, Fedora тощо)

### Крок 1. Завантажте проєкт

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Крок 2. Перевірте, що працює

```bash
./start.sh          # або: uvicorn backend.main:app --port 8000
```

Відкрийте `http://127.0.0.1:8000`.

### Крок 3 (опційно). Автозапуск через systemd (user unit)

```bash
mkdir -p ~/.config/systemd/user
cp scripts/folio-local.service ~/.config/systemd/user/
# відредагуйте шлях /opt/folio-local на свій у файлі юніта:
${EDITOR:-nano} ~/.config/systemd/user/folio-local.service
systemctl --user daemon-reload
systemctl --user enable --now folio-local
systemctl --user status folio-local   # має бути active (running)
```

Щоб сервіс працював і без активного сеансу SSH:

```bash
sudo loginctl enable-linger $USER
```

Корисні команди: `systemctl --user restart folio-local`,
`journalctl --user -u folio-local -f` (логи).

### Альтернатива: деплой одним скриптом (без Docker)

```bash
./scripts/deploy-local.sh                 # venv + залежності + база + сервер
./scripts/deploy-local.sh --install-only  # тільки підготувати, сервер не запускати
FOLIO_HOST=0.0.0.0 FOLIO_PORT=8080 ./scripts/deploy-local.sh
```

Скрипт створює `.venv`, ставить `requirements.txt`, ініціалізує `folio.db`
і запускає `uvicorn backend.main:app` — добре пасує до systemd-юніта вище.

---

## Оновлення

```bash
cd folio-local
git pull            # або розпакуйте новий ZIP поверх
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# перезапустіть сервер (Ctrl+C у вікні start.bat / systemctl --user restart folio-local)
```

**Перед оновленням зробіть бекап**: у інтерфейсі кнопка
«Завантажити бекап (.db)» — або просто скопіюйте файл `folio.db` кудись у
безпечне місце. Ваші дані живуть тільки в цьому одному файлі.

## Доступ по паролю (опційно)

Якщо сервер бачить не лише ваш комп'ютер (reverse proxy, VPN, домашня мережа),
увімкніть single-user Basic auth — задайте обидві змінні середовища перед
запуском сервера:

- Linux/macOS: `export FOLIO_AUTH_USER="alice"` та `export FOLIO_AUTH_PASSWORD="..."` (або пропишіть їх у юніті `folio-local.service` у секції `[Service]` як `Environment=...`).
- Windows: `$env:FOLIO_AUTH_USER="alice"` та `$env:FOLIO_AUTH_PASSWORD="..."` у PowerShell перед `start.bat`.

Тоді кожна сторінка, крім `/api/health`, вимагатиме логін і пароль (HTTP 401
інакше). Використовуйте цю автентифікацію тільки за HTTPS — TLS має
термінувати reverse proxy.

## Опціонально: нативне ядро (.NET 10) для швидшої математики

XIRR/TWR можна прискорити, зібравши нативне C#-ядро. Це **не обов'язково**:
без нього застосунок працює так само (Python-реалізація використовується
автоматично).

1. Встановіть [.NET SDK 10](https://dotnet.microsoft.com/download) (безкоштовно).
2. Зберіть ядро:
   - Windows: `scripts\build_native.bat`
   - Linux/macOS: `./scripts/build_native.sh`
3. Перезапустіть сервер. `backend/native_accel.py` знайде exe автоматично
   (або вкажіть шлях у змінній середовища `FOLIO_NATIVE`).

Результат — самодостатній exe (~70 MB) у
`dotnet/FolioCli/bin/Release/net10.0/<platform>/publish/`; .NET-рантайм
для роботи сервера не потрібен. Деталі та заміри швидкості — у README
(розділ «Нативне ядро»).

## Де живуть мої дані?

У файлі `folio.db` у папці проєкту (або шлях із змінної середовища `FOLIO_DB`).
Резервна копія — кнопка в UI або `GET /api/backup`. Відновлення — кнопка
«Відновити з файлу». Видалити все = видалити `folio.db`.

## Часті проблеми

| Симптом | Рішення |
|---|---|
| `python не є внутрішньою або зовнішньою командою` | Перевстановіть Python з галочкою «Add to PATH» |
| Порт 8000 зайнятий | `start.bat` автоматично шукає вільний порт; або задайте `FOLIO_PORT` |
| Браузер не відкрився сам | Відкрийте вручну `http://127.0.0.1:8000` |
| Ціни не завантажуються | Перевірте інтернет; Stooq/CoinGecko можуть тимчасово не відповідати |

---

# INSTALL (English)

1. Install Python 3.12+ (Windows: tick *Add python.exe to PATH*).
2. Get the project: `git clone https://github.com/bigpi/folio-local.git`
   (or Download ZIP).
3. **Windows**: double-click `start.bat` — it creates the venv, installs
   dependencies, starts the server and opens `http://127.0.0.1:8000`.
   **Linux**: `python3 -m venv .venv && source .venv/bin/activate &&
   pip install -r requirements.txt && ./start.sh`.
4. Optional autostart: Windows — copy a shortcut to `start.bat` into the
   `shell:startup` folder; Linux — systemd user unit in
   `scripts/folio-local.service` (`systemctl --user enable --now folio-local`).
5. Updating: `git pull && pip install -r requirements.txt`, restart the
   server. Back up `folio.db` (one click in the UI) beforehand.
6. All data lives in the single local file `folio.db`. Nothing leaves your
   machine.
