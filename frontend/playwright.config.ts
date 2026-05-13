import { defineConfig, devices } from "@playwright/test";

/**
 * PR-BL-3 (Phase 4-I): Playwright e2e 설정.
 *
 * 1차 — chromium만, e2e 디렉터리는 `e2e/`(vitest의 `**\/*.test.ts`와 분리).
 * webServer로 next dev 자동 실행 — 별도 backend 필요 없는 smoke만 우선
 * (auth/dashboard는 backend mock 또는 cookie injection 패턴이 정착된 후 추가).
 *
 * vitest와 file pattern이 안 겹치도록 testDir + testMatch 명시.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
