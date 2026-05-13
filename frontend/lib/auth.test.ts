import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { clearAuth, getUser, isLoggedIn, saveAuth } from "./auth";
import type { UserInfo } from "./types";

const SAMPLE_USER: UserInfo = {
  id: 1,
  username: "test",
  name: "테스터",
  email: "test@dyce.kr",
  role: "admin",
  status: "active",
  notion_user_id: "",
  midas_url: "",
  has_midas_key: false,
  work_dir: "",
  last_login_at: null,
};

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

afterEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

/**
 * PR-BN — saveAuth backward-compat (INCIDENT 체크리스트 #2).
 *
 * Vercel chunk 부분 stale 시 옛 호출(token, user)과 새 호출(user)이 혼재해도
 * user JSON이 항상 유효하게 저장되어야 함. PR-BI 사고 재발 방지.
 */
describe("saveAuth backward-compat", () => {
  it("legacy 2-인자 (token, user) — 둘 다 localStorage에 저장", () => {
    saveAuth("legacy-token", SAMPLE_USER);
    expect(localStorage.getItem("dy_auth_token")).toBe("legacy-token");
    expect(getUser()).toEqual(SAMPLE_USER);
  });

  it("새 1-인자 (user) — token 저장 안 함, user만 저장", () => {
    saveAuth(SAMPLE_USER);
    expect(localStorage.getItem("dy_auth_token")).toBeNull();
    expect(getUser()).toEqual(SAMPLE_USER);
  });

  it("clearAuth 호출 시 token + user 모두 제거 + logged_out flag 설정", () => {
    saveAuth("t", SAMPLE_USER);
    expect(isLoggedIn()).toBe(true);
    clearAuth();
    expect(localStorage.getItem("dy_auth_token")).toBeNull();
    expect(localStorage.getItem("dy_auth_user")).toBeNull();
    expect(sessionStorage.getItem("dy_logged_out")).toBe("1");
  });
});
