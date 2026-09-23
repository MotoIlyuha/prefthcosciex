import { defineConfig, devices } from "@playwright/test";

// End-to-end runs against a live stack: API with DEV_LOGIN=true and the client built
// with VITE_E2E=1 (see docs/RUNBOOK.md, «E2E»). PW_CHROMIUM points at a system
// Chromium when the bundled one is not installed.
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:4173",
    trace: "retain-on-failure",
    locale: "ru-RU",
    timezoneId: "Europe/Moscow",
  },
  projects: [
    {
      name: "mobile",
      use: {
        ...devices["Pixel 7"],
        launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {},
      },
    },
  ],
});
