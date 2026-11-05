# Security Policy / Політика безпеки

## Reporting a vulnerability / Як повідомити про вразливість

**Do NOT open a public issue for security vulnerabilities.**
**НЕ створюйте публічний issue для вразливостей.**

Report privately, either:

- via GitHub **Private vulnerability reporting** (Security → Report a
  vulnerability) on this repository, or
- via the contact on the owner's GitHub profile.

**Українською:** повідомляйте приватно — через «Private vulnerability
reporting» у вкладці Security цього репозиторію, або через контакти
власника в профілі GitHub. Опишіть: версію, кроки відтворення, вплив.
Відповідь — протягом 7 днів.

## Scope / Що вважаємо вразливістю

folio-local is a **local-only** app by design:

- No authentication is a deliberate choice: the server binds to
  `127.0.0.1` only. Exposing it to a network without adding auth yourself
  is not a supported configuration (but if the app binds to `0.0.0.0` by
  default anywhere — that IS a bug, please report it).
- Price/FX data are fetched from public sources (Stooq, CoinGecko, ECB) —
  any injection through those responses is in scope.
- Anything that sends user data off the device is in scope.

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ |
| < 1.0   | ❌ |
