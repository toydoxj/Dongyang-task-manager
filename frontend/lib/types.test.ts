import { describe, expect, it } from "vitest";

import { ROLE_LABEL, type UserRole } from "./types";

/**
 * ROLE_LABEL — 4 role의 한글 표기. Sidebar/AuthGuard/UI 다수에서 사용 (UX 일관성).
 * member의 표기가 "일반직원"이라는 점이 고객 요구사항 (CLAUDE.md / USER_MANUAL.md).
 */
describe("ROLE_LABEL", () => {
  it("4개 role 모두 정의됨", () => {
    const roles: UserRole[] = ["admin", "team_lead", "manager", "member"];
    for (const r of roles) {
      expect(ROLE_LABEL[r]).toBeDefined();
      expect(ROLE_LABEL[r]).not.toBe("");
    }
  });

  it("표준 한글 표기 — 회귀 방지", () => {
    expect(ROLE_LABEL.admin).toBe("관리자");
    expect(ROLE_LABEL.team_lead).toBe("팀장");
    expect(ROLE_LABEL.manager).toBe("관리팀");
    expect(ROLE_LABEL.member).toBe("일반직원");
  });
});
