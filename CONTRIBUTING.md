# Contributing to folio-local / Як долучитися

> Укр + EN у одному файлі. Дякуємо за інтерес до проєкту!
> Thanks for your interest in the project!

## Налаштування середовища / Environment setup

```bash
git clone https://github.com/bigpi/folio-local.git
cd folio-local
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
```

## Запуск тестів / Running tests

```bash
pytest -q          # весь набір (140+ тестів, швидко, без мережі)
pytest tests/test_xirr.py -q   # один файл
```

Тести не мають вимагати інтернету. Смоук-тест живого сервера:
`bash scripts/smoke.sh`.

## Стиль комітів / Commit style

- Формат: `Зона: короткий опис` — наприклад
  `Presets: Fidelity dividend rows` або `UI: fix chart resize`.
- Одна логічна зміна = один commit. Тест на кожну фічу/фіксу.
- Ukrainian or English description is fine; no machine-translated filler.

## Як запропонувати фічу / Proposing a feature

1. Відкрийте issue з шаблоном **Feature request** — опишіть проблему, яку
   ви вирішуєте, а не тільки рішення.
2. Для змін у фінансовій математиці (XIRR/TWR/FX) — спершу обговорення:
   математика тут свідома і задокументована в README.
3. PR: маленькі, з тестом, зелений `pytest`. Без нових обов'язкових
   залежностей (стандартна бібліотека > нова бібліотека).

## Правила, які не обговорюються / Non-negotiable rules

- **Ніколи не додавати російську локалізацію** (політичне рішення власника
  проєкту). UA/EN only. Ever.
- Жодних телеметрії, трекерів, аналітики — це privacy-first проєкт.
- Жодних абсолютних шляхів, токенів чи персональних даних у коді.
- Дані користувача не залишають його пристрій — не додавайте нічого,
  що надсилає їх кудись.
