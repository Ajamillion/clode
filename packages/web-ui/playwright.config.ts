import { defineConfig } from '@playwright/test'
import path from 'node:path'

const ROOT = path.resolve(__dirname, '..', '..')

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: true,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: 'pnpm --filter @bagger/dev-mocks dev',
      cwd: ROOT,
      port: 8787,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'pnpm --filter @bagger/web-ui dev',
      cwd: ROOT,
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
