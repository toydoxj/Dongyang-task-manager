import { expect, test } from "@playwright/test";

import { mockAuthChannelStats, setupRoleAuth } from "./_helpers";

/** PR-EY: /admin/auth-stats verdict 분기 회귀 검증.
 *
 * 임계값(GO 0.99 / 관찰 0.95 / NO-GO < 0.95) 변경 또는 응답 schema 변경 시
 * 자동 검출. PR-ES backend endpoint + PR-ET frontend UI 통합 회귀 시나리오.
 *
 * mockBackendEmpty 사용 안 함 — catch-all `/api/**`이 specific routes 우선
 * 매칭을 깨뜨려 auth/status가 빈 객체 반환 → 로그인 화면 분기. role-access
 * 패턴: backend 미가동 → AuthGuard catch fallback → ready phase 진입.
 * `/api/auth/channel-stats`만 mock + 다른 fetch는 catch fallback에 의존.
 */
const VISIBLE_TIMEOUT = 15_000;

test.describe("/admin/auth-stats verdict 분기 (PR-EY)", () => {
  test.beforeEach(async ({ page }) => {
    await setupRoleAuth(page, "admin");
  });

  test("cookie_ratio ≥ 0.99 → GO verdict", async ({ page }) => {
    // header=5, cookie=995 → ratio 0.995
    await mockAuthChannelStats(page, { header: 5, cookie: 995 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/GO — 5차 재시도 안전/)).toBeVisible({
      timeout: 5000,
    });
    // 카운터 표시 확인 (콤마 포함 1,000)
    await expect(page.getByText("995").first()).toBeVisible();
  });

  test("0.95 ≤ ratio < 0.99 → 관찰 verdict", async ({ page }) => {
    // header=40, cookie=960 → ratio 0.96
    await mockAuthChannelStats(page, { header: 40, cookie: 960 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/관찰 지속/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });

  test("ratio < 0.95 → NO-GO verdict (header fallback 의존 잔존)", async ({
    page,
  }) => {
    // header=500, cookie=500 → ratio 0.5
    await mockAuthChannelStats(page, { header: 500, cookie: 500 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/NO-GO/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await expect(
      page.getByText(/header fallback 의존 잔존/),
    ).toBeVisible();
  });

  test("total=0 → 데이터 없음 (verdict idle)", async ({ page }) => {
    await mockAuthChannelStats(page, { header: 0, cookie: 0 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/데이터 없음/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });
});
