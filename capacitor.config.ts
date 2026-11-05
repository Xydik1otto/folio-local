import type { CapacitorConfig } from '@capacitor/cli';

/**
 * folio-local mobile shell.
 *
 * This app has NO bundled UI. It shows a one-time splash where the user
 * enters the address of their own folio-local server (self-hosted ethos),
 * stores it and then navigates the WebView to that server. Reach the server
 * over LAN or a VPN (Tailscale/WireGuard) — see MOBILE.md.
 */
const config: CapacitorConfig = {
  appId: 'io.github.xydik1otto.folio_local',
  appName: 'folio-local',
  webDir: 'www',
  android: {
    allowMixedContent: true,
  },
  server: {
    // No fixed server.url: the user chooses their own server on first launch.
    // Allow navigation to any user-specified host (self-hosted, LAN, VPN).
    allowNavigation: ['*'],
  },
};

export default config;
