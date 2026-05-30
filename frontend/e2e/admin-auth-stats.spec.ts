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

  test("cookie_ready_ratio ≥ 0.99 → GO verdict", async ({ page }) => {
    // header 요청 5건도 모두 유효 cookie 보유 → cookie-only 준비율 100%
    await mockAuthChannelStats(page, {
      header: 5,
      cookie: 995,
      headerWithValidCookie: 5,
    });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/GO — 5차 재시도 안전/)).toBeVisible({
      timeout: 5000,
    });
    // cookie-only 통과 가능 카운터 표시 확인 (995 + 5 = 1,000)
    await expect(page.getByText("1,000").first()).toBeVisible();
  });

  test("0.95 ≤ cookie_ready_ratio < 0.99 → 관찰 verdict", async ({ page }) => {
    // cookie 920 + valid cookie header 40 / 전체 1,000 → 준비율 96%
    await mockAuthChannelStats(page, {
      header: 80,
      cookie: 920,
      headerWithValidCookie: 40,
    });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/관찰 지속/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });

  test("cookie_ready_ratio < 0.95 → NO-GO verdict", async ({
    page,
  }) => {
    // header 500건 모두 cookie 없음 → 준비율 50%
    await mockAuthChannelStats(page, { header: 500, cookie: 500 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/NO-GO/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await expect(
      page.getByText(/cookie-only 차단 요청 잔존/),
    ).toBeVisible();
  });

  test("total=0 → 데이터 없음 (verdict idle)", async ({ page }) => {
    await mockAuthChannelStats(page, { header: 0, cookie: 0 });
    await page.goto("/admin/auth-stats");
    await expect(page.getByText(/데이터 없음/)).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });
});
