import { expect, test } from "@playwright/test";

import { setupRoleAuth } from "./_helpers";

/**
 * PR-BL-5 — 4 role 인증/접근 시나리오 (PR-BI 회귀 정밀 검출 안전망).
 *
 * backend는 e2e 환경에서 미가동 → checkAuthStatus가 fetch 실패 → AuthGuard catch
 * fallback으로 `setUser(getUser()) + setPhase("ready")` 진입(Phase 0-B 추가 fix
 * 덕분에 backend down에도 가드 정상 동작). localStorage에 user JSON만 미리 주입
 * 하면 page.tsx의 role guard가 평가됨.
 *
 * 검증 포인트:
 * - admin / team_lead / manager → 루트(/) 진입 시 대시보드 헤더 노출
 * - member → / 진입 시 /me로 redirect (대시보드 접근 차단)
 *
 * 페이지가 깨지면(예: PR-BI 같은 redirect loop) 단언이 timeout으로 실패한다.
 * 더 정밀한 backend mock e2e는 별도 cycle (msw 또는 SSR proxy 패턴 정착 후).
 */

const VISIBLE_TIMEOUT = 30_000;

test.describe("4 role 접근 시나리오", () => {
  for (const role of ["admin", "team_lead", "manager"] as const) {
    test(`${role} — 루트 진입 시 대시보드 헤더 노출`, async ({ page }) => {
      await setupRoleAuth(page, role);
      await page.goto("/");

      await expect(
        page.getByRole("heading", { name: "대시보드", level: 1 }),
      ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    });
  }

  test("member — 루트 진입 시 /me로 redirect", async ({ page }) => {
    await setupRoleAuth(page, "member");
    await page.goto("/");

    await page.waitForURL(/\/me/, { timeout: VISIBLE_TIMEOUT });
  });
});
