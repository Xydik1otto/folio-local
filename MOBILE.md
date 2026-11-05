# 📱 folio-local на мобільних / folio-local on mobile

> Укр + EN в одному файлі. Мобільний порт — на гілці `mobile/android-ios`
> (Capacitor 6; master залишається стабільною веб-версією).
> Mobile port lives on the `mobile/android-ios` branch (Capacitor 6; master
> stays the stable web version).

## Як це працює / How it works

Мобільний застосунок — **оболонка без власного UI** (Capacitor WebView).
При першому запуску він показує екран із полем «Адреса сервера»: введіть
адресу **вашого власного** сервера folio-local — далі застосунок показує
звичайний веб-інтерфейс з цього сервера. Дані залишаються на вашому сервері.

The mobile app is a **shell without its own UI** (Capacitor WebView). On
first launch it shows a screen with a "Server address" field: enter the
address of **your own** folio-local server — the app then renders the normal
web UI from that server. Your data stays on your server.

## Android (безкоштовно) / Android (free)

1. Скачайте APK зі сторінки [Releases](https://github.com/bigpi/folio-local/releases)
   (артефакти CI також доступні у вкладці Actions, 30 днів) або зберіть локально:
   ```bash
   npm ci && npx cap sync android
   cd android && ./gradlew assembleDebug
   # → android/app/build/outputs/apk/debug/app-debug.apk
   ```
2. Дозвольте «Встановлення невідомих застосунків» для вашого файлового
   менеджера і встановіть APK. Android 7.0 → 16 (minSdk 24, targetSdk 35).

1. Download the APK from [Releases](https://github.com/bigpi/folio-local/releases)
   (CI artifacts are also under the Actions tab, kept 30 days) or build locally
   (see the command above).
2. Allow "Install unknown apps" for your file manager and install the APK.
   Supports Android 7.0 → 16 (minSdk 24, targetSdk 35).

## iOS: AltStore / Sideloadly (безкоштовно) / iOS via AltStore (free)

App Store вимагає Apple Developer ($99/рік) — цього немає в бюджеті проєкту,
тому офіційного App Store-рілізу **не буде**. Шлях: unsigned-збірка з CI
(Actions → ios-build → артефакт `folio-local-ios-unsigned.zip`) →
встановлення через [AltStore](https://altstore.io/) або
[Sideloadly](https://sideloadly.io/) з безкоштовним Apple ID (потребує
re-sign кожні 7 днів) або через платний Apple Developer акаунт, якщо він у вас є.

The App Store requires an Apple Developer account ($99/year) — out of the
project's budget, so there will be **no** App Store release. The path is:
unsigned CI build (Actions → ios-build → artifact
`folio-local-ios-unsigned.zip`) → install with
[AltStore](https://altstore.io/) or [Sideloadly](https://sideloadly.io/)
using a free Apple ID (re-sign every 7 days), or with your own paid account.

## Збірка iOS локально / Building iOS locally

Потрібні macOS + Xcode 15+:

```bash
npm ci && npx cap sync ios
cd ios/App && pod install
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -destination 'generic/platform=iOS' CODE_SIGNING_ALLOWED=NO build
```

## Доступ до свого сервера / Reaching your server

Мобільний застосунок підключається лише до адреси, яку ви вказали. Типові
варіанти:

- **Домашня Wi-Fi мережа**: `http://192.168.x.x:8000` (HTTP у LAN дозволено:
  `usesCleartextTraffic` на Android, ATS-виняток в Info.plist на iOS).
- **З-за межами дому — Tailscale/WireGuard (безкоштовно)**:
  1. Встановіть Tailscale на сервер і на телефон, увійдіть в один акаунт.
  2. Адреса сервера в Tailscale-мережі — `http://100.x.y.z:8000`
     (IP дивіться в Tailscale: `tailscale ip -4`).
  3. Введіть цю адресу на splash-екрані застосунку.

The app connects only to the address you provide. Typical setups:

- **Home Wi-Fi**: `http://192.168.x.x:8000` (plain HTTP on LAN is allowed:
  `usesCleartextTraffic` on Android, ATS exception in Info.plist on iOS).
- **Away from home — Tailscale/WireGuard (free)**:
  1. Install Tailscale on the server and the phone, sign in to one account.
  2. The server's Tailscale address is `http://100.x.y.z:8000`
     (see `tailscale ip -4`).
  3. Enter that address on the app's splash screen.

## Конфігурація / Configuration

- `capacitor.config.ts` — appId `io.github.xydik1otto.folio_local`,
  `server.allowNavigation: ['*']` (довільний self-hosted сервер).
- Android: `android/variables.gradle` (minSdk 24, targetSdk 35).
- iOS: `ios/App/App.xcodeproj/project.pbxproj` (iOS 14.0),
  `ios/App/App/Info.plist` (ATS).

- `capacitor.config.ts` — appId `io.github.xydik1otto.folio_local`,
  `server.allowNavigation: ['*']` (arbitrary self-hosted server).
- Android: `android/variables.gradle` (minSdk 24, targetSdk 35).
- iOS: `ios/App/App.xcodeproj/project.pbxproj` (iOS 14.0),
  `ios/App/App/Info.plist` (ATS).
