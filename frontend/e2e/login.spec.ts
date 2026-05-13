import { expect, test } from "@playwright/test";

/**
 * PR-BL-3 (Phase 4-I): /login 화면 노출 smoke.
 *
 * 1차 — backend 의존 없는 가장 narrow한 시나리오. /login 직접 진입 후 NAVER WORKS
 * 로그인 안내 텍스트가 노출되는지 확인. PR-BI 같은 회귀(로그인 화면 자체가 깨짐)
 * 를 가장 빠르게 검출.
 *
 * AuthGuard redirect / cookie hydration 등 backend 의존 흐름은 다음 cycle
 * (backend mock fixture 정착 후).
 */
test.describe("로그인 화면", () => {
  test("/login 직접 진입 시 헤더 노출", async ({ page }) => {
    // ?error=test로 진입 — worksEnabled가 true여도 자동 외부 redirect 없이
    // errorMessage 분기 화면이 노출됨 (backend 의존 회피).
    await page.goto("/login?error=test");

    // 항상 노출되는 페이지 헤더(role=heading, level 1). PR-BI 같은 redirect loop이
    // 발생하면 timeout. sidebar의 "업무관리"는 h1 아니므로 strict 충돌 없음.
    await expect(
      page.getByRole("heading", { name: "업무관리 시스템", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("heading", { name: "로그인 실패" }),
    ).toBeVisible();
    await expect(page.getByText("회사 NAVER WORKS")).toBeVisible();
  });
});
