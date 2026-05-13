import type { Page, Route } from "@playwright/test";

/** 4 role e2e fixture — localStorage 인증 + API mock 셋업.
 *
 * AuthGuard는 isLoggedIn() 단계에서 localStorage(dy_auth_token + dy_auth_user)
 * 만 보고 ready phase로 진입. 페이지 컴포넌트가 호출하는 SWR endpoint는 모두
 * 빈 응답으로 mock — backend 의존 없는 self-contained e2e.
 */
export type Role = "admin" | "team_lead" | "manager" | "member";

const ROLE_USER = {
  admin: { id: 1, username: "admin", name: "관리자", role: "admin" },
  team_lead: { id: 2, username: "lead", name: "팀장", role: "team_lead" },
  manager: { id: 3, username: "office", name: "관리팀", role: "manager" },
  member: { id: 4, username: "member", name: "직원", role: "member" },
};

function userJson(role: Role): string {
  const u = ROLE_USER[role];
  return JSON.stringify({
    ...u,
    email: `${u.username}@dyce.kr`,
    status: "active",
    notion_user_id: "",
    midas_url: "",
    has_midas_key: false,
    work_dir: "",
    auth_provider: "works",
  });
}

/** 페이지 mount 전에 localStorage에 인증 정보 주입. */
export async function setupRoleAuth(page: Page, role: Role): Promise<void> {
  await page.addInitScript(
    ({ token, user }) => {
      window.localStorage.setItem("dy_auth_token", token);
      window.localStorage.setItem("dy_auth_user", user);
    },
    { token: `mock-${role}-token`, user: userJson(role) },
  );
}

// frontend(localhost:3000) ↔ backend(127.0.0.1:8000 default) cross-origin이라
// preflight OPTIONS 발생. mock fulfill에 항상 CORS header 포함 + OPTIONS 204 처리.
const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,PATCH,PUT,DELETE,OPTIONS",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Credentials": "true",
};

function fulfillJson(route: Route, body: object): void {
  if (route.request().method() === "OPTIONS") {
    void route.fulfill({ status: 204, headers: CORS_HEADERS, body: "" });
    return;
  }
  void route.fulfill({
    status: 200,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** 대시보드/페이지 컴포넌트가 호출하는 backend endpoint를 모두 빈 응답으로 mock. */
export async function mockBackendEmpty(page: Page): Promise<void> {
  await page.route("**/api/auth/status", (r) =>
    fulfillJson(r, {
      initialized: true,
      user_count: 4,
      works_enabled: true,
      works_drive_local_root: "",
    }),
  );

  await page.route("**/api/auth/me", (r) => fulfillJson(r, {}));

  await page.route("**/api/dashboard/**", (r) => {
    const path = new URL(r.request().url()).pathname;
    let body: object = {};
    if (path.endsWith("/summary")) {
      body = {
        in_progress_count: 0,
        stalled_count: 0,
        due_soon_tasks: 0,
        pending_seal_count: 0,
        week_income: 0,
        week_expense: 0,
        top_team: null,
        today: "2026-05-13",
        week_start: "2026-05-11",
        week_end: "2026-05-18",
      };
    } else if (path.endsWith("/actions")) {
      body = {
        stalled_projects: { count: 0, preview: "" },
        overdue_seals: { count: 0, preview: "" },
        due_soon_tasks: { count: 0, preview: "" },
        overloaded_team: { count: 0, preview: "" },
        stuck_tasks: { count: 0, preview: "" },
      };
    } else if (path.endsWith("/insights")) {
      body = { recent_updates: [], warnings: [] };
    }
    fulfillJson(r, body);
  });

  await page.route("**/api/projects**", (r) =>
    fulfillJson(r, { items: [], count: 0 }),
  );
  await page.route("**/api/tasks**", (r) =>
    fulfillJson(r, { items: [], count: 0 }),
  );
  await page.route("**/api/cashflow**", (r) =>
    fulfillJson(r, { items: [], count: 0 }),
  );
  await page.route("**/api/seal-requests**", (r) =>
    fulfillJson(r, { items: [], count: 0 }),
  );
  await page.route("**/api/clients**", (r) =>
    fulfillJson(r, { items: [], count: 0 }),
  );

  // 그 외 모든 /api/* 호출은 빈 객체로 fallback (e2e 깨짐 방지)
  await page.route("**/api/**", (r) => fulfillJson(r, {}));
}
