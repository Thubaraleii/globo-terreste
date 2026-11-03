// E2E com o navegador ja instalado (Edge; Chrome com GEOWORLD_BROWSER=chrome).
// Nunca baixa navegador: nao rode `npx playwright install`.
import { defineConfig } from '@playwright/test';

const PORT = 8767; // diferente de `npm run serve` (8766)
const channel = process.env.GEOWORLD_BROWSER === 'chrome' ? 'chrome' : 'msedge';

export default defineConfig({
  testDir: 'tests/e2e',
  testMatch: '**/*.spec.js',
  globalSetup: './tests/e2e/global-setup.mjs',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  timeout: 60_000,
  use: {
    channel,
    baseURL: `http://127.0.0.1:${PORT}`,
    headless: true,
    viewport: { width: 1280, height: 800 },
  },
  webServer: {
    command: 'node tests/e2e/static-server.mjs',
    url: `http://127.0.0.1:${PORT}/index.html`,
    reuseExistingServer: false,
    env: { PORT: String(PORT) },
  },
});
