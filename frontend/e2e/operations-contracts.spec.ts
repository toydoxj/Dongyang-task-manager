import { expect, test } from "@playwright/test";

import { setupRoleAuth } from "./_helpers";

/**
 * PR-FH/4 — `/operations/contracts` 페이지 4역할 진입 시나리오.
 *
 * 가드 정합 검증.
 * - admin / team_lead / manager → 페이지 헤더 + 「+ 새 계약서」 노출
 * - member → UnauthorizedRedirect 메시지
 *
 * PR-EY 학습: mockBackendEmpty의 `/api/auth/me` 빈 mock은 AuthGuard가 user role을
 * 빈 문자열로 set해 가드를 차단시킴. setupRoleAuth만 사용 — AuthGuard catch
 * fallback이 localStorage user를 채택 (role-access 패턴 동일).
 *
 * SWR fetch는 network fail로 끝나지만 페이지 헤더·버튼은 렌더되며, 가드 평가만
 * 검증하는 목적상 fetch 실패는 무관.
 */

const VISIBLE_TIMEOUT = 30_000;

test.describe("계약서 관리 (operations/contracts) 4역할 가드", () => {
  for (const role of ["admin", "team_lead", "manager"] as const) {
    test(`${role} — 페이지 헤더 + 새 계약서 버튼 노출`, async ({ page }) => {
      await setupRoleAuth(page, role);
      await page.goto("/operations/contracts");

      await expect(
        page.getByRole("heading", { name: "계약서 관리", level: 1 }),
      ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
      await expect(
        page.getByRole("button", { name: /새 계약서/ }),
      ).toBeVisible();
    });
  }

  test("member — UnauthorizedRedirect 메시지 노출", async ({ page }) => {
    await setupRoleAuth(page, "member");
    await page.goto("/operations/contracts");

    await expect(
      page.getByText("계약서 관리 권한이 없습니다."),
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });
});
