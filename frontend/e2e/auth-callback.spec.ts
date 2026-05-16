import { expect, test } from "@playwright/test";

import { makeCallbackFragment, mockAuthMe, mockBackendEmpty } from "./_helpers";

/** PR-EP (INCIDENT #4/#5 체크리스트 #5 충족) — callback page의 verifyAndHydrateFromMe
 * (PR-CY+PR-EO) 동작을 실제 브라우저 흐름으로 검증.
 *
 * PR-EM/EN 회귀(cookie 발급 안 된 사용자에서 401 무한)를 모델링 — fragment user는
 * 정상이지만 /api/auth/me 401인 경우 graceful fallback이 동작해 redirect는 진행돼야
 * 함. silent SSO trigger 안 함 (callback page 무한 재귀 회피).
 */
test.describe("callback page — verifyAndHydrateFromMe (PR-CY + PR-EO)", () => {
  test.beforeEach(async ({ page }) => {
    await mockBackendEmpty(page);
  });

  test("/api/auth/me 200 → redirect + localStorage user 갱신", async ({
    page,
  }) => {
    const responseUser = {
      id: 99,
      username: "renamed",
      name: "이름갱신됨",
      role: "admin",
      email: "renamed@dyce.kr",
      status: "active",
      notion_user_id: "",
      midas_url: "",
      has_midas_key: false,
      work_dir: "",
    };
    await mockAuthMe(page, { status: 200, user: responseUser });

    const fragment = makeCallbackFragment("admin", "/dashboard");
    await page.goto(`/auth/works/callback${fragment}`);

    // redirect 완료 대기 — callback page가 window.location.replace로 hard navigate
    await page.waitForURL("**/dashboard", { timeout: 5000 });

    const storedUser = await page.evaluate(() =>
      window.localStorage.getItem("dy_auth_user"),
    );
    expect(storedUser).not.toBeNull();
    const parsed = JSON.parse(storedUser!) as { name: string };
    expect(parsed.name).toBe("이름갱신됨"); // 응답 user로 갱신됨
  });

  test("/api/auth/me 401 → graceful warn + redirect (fragment user fallback)", async ({
    page,
  }) => {
    await mockAuthMe(page, { status: 401 });

    const warnings: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "warning") warnings.push(msg.text());
    });

    const fragment = makeCallbackFragment("admin", "/dashboard");
    await page.goto(`/auth/works/callback${fragment}`);

    // graceful — 401이어도 redirect 진행 (INCIDENT #4 무한 재귀 회피)
    await page.waitForURL("**/dashboard", { timeout: 5000 });

    // warn 메시지 + fragment user는 그대로 (saveAuth로 저장됐고 saveAuth(user) 호출 X)
    expect(warnings.some((w) => w.includes("/me 401"))).toBe(true);
    const storedUser = await page.evaluate(() =>
      window.localStorage.getItem("dy_auth_user"),
    );
    expect(storedUser).not.toBeNull();
    const parsed = JSON.parse(storedUser!) as { username: string };
    expect(parsed.username).toBe("admin"); // fragment 값 그대로
  });

  test("/api/auth/me network fail → graceful warn + redirect", async ({
    page,
  }) => {
    await mockAuthMe(page, { status: 200, fail: true });

    const warnings: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "warning") warnings.push(msg.text());
    });

    const fragment = makeCallbackFragment("member", "/me");
    await page.goto(`/auth/works/callback${fragment}`);

    // network fail이어도 redirect 진행 — backend down 상황에서 graceful
    await page.waitForURL("**/me", { timeout: 5000 });

    expect(warnings.some((w) => w.includes("/me network fail"))).toBe(true);
  });
});
