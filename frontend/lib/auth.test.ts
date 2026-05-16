import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  authFetch,
  clearAuth,
  getUser,
  isLoggedIn,
  saveAuth,
  verifyAndHydrateFromMe,
} from "./auth";
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

/**
 * PR-BO (INCIDENT 체크리스트 #3) — authFetch 401 응답 시 silent SSO 1회 재시도.
 * 같은 탭에서 silent 이미 실패 / 명시 logout 직후엔 즉시 cleanup + redirect.
 */
describe("authFetch 401 handling", () => {
  it("200은 그대로 반환 — 추가 처리 없음", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 200 }));
    saveAuth("t", SAMPLE_USER);

    const res = await authFetch("/api/test");
    expect(res.status).toBe(200);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    fetchSpy.mockRestore();
  });

  it("logged_out flag가 있으면 401 시 silent 재시도 안 하고 즉시 cleanup", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);
    sessionStorage.setItem("dy_logged_out", "1");
    // jsdom location.href 할당은 noop이지만 에러 없이 통과해야
    const res = await authFetch("/api/test");
    expect(res.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1); // silent 재시도 X
    expect(getUser()).toBeNull(); // clearAuth 호출됨
    fetchSpy.mockRestore();
  });

  it("silent SSO 이미 실패 flag가 있으면 401 시 재시도 안 함", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);
    sessionStorage.setItem("dy_silent_failed", "1");

    const res = await authFetch("/api/test");
    expect(res.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(getUser()).toBeNull();
    fetchSpy.mockRestore();
  });

  /**
   * PR-DV (INCIDENT #5 체크리스트 #3) — 인증 검증 endpoint는 401에 silent SSO
   * trigger 안 함. 현재 callsite 없지만 미래 회귀 방지.
   */
  it("/api/auth/me 401은 silent SSO 재시도 X — 즉시 cleanup", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);

    const res = await authFetch("/api/auth/me");
    expect(res.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1); // silent SSO trigger X
    expect(getUser()).toBeNull(); // clearAuth
    fetchSpy.mockRestore();
  });

  it("/api/auth/status 401도 silent SSO 재시도 X — 즉시 cleanup", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);

    const res = await authFetch("/api/auth/status");
    expect(res.status).toBe(401);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(getUser()).toBeNull();
    fetchSpy.mockRestore();
  });
});

/**
 * PR-CX (INCIDENT #1 체크리스트 #3) — silent_failed flag TTL 회복.
 *
 * 기존: 같은 탭에서 silent SSO 한 번 실패 시 영구 차단 → cookie 만료 후
 * 사용자 회복 불가 (새로고침 안 하면 loop).
 * 수정: timestamp 기반 5분 TTL — 만료 후 자동 재시도 허용.
 * legacy "1" 값은 fresh fail로 간주해 timestamp marker로 자동 갱신.
 */
describe("silent SSO flag TTL 회복 (PR-CX)", () => {
  it("legacy '1' 값은 authFetch 401 시 fresh timestamp로 자동 갱신됨", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);
    sessionStorage.setItem("dy_silent_failed", "1");

    await authFetch("/api/test");

    // 401 처리 흐름에서 _isSilentFailedRecently가 호출되어 "1" → timestamp marker로 갱신
    const raw = sessionStorage.getItem("dy_silent_failed");
    expect(raw).not.toBeNull();
    expect(raw).not.toBe("1");
    const ts = Number(raw);
    expect(Number.isFinite(ts)).toBe(true);
    // 갱신된 timestamp는 현재 시점에서 1초 이내 (test 실행 즉시)
    expect(Date.now() - ts).toBeLessThan(1000);
    fetchSpy.mockRestore();
  });

  it("5분 전 timestamp는 stale로 간주되어 silent 재시도 허용 (회복 동작)", async () => {
    // 첫 401: 5분+1초 전 timestamp → _isSilentFailedRecently=false → silent SSO 시도
    // 단 silent SSO는 iframe — jsdom에서 timeout 후 _markSilentFailed로 fresh marker
    // 그 다음 _markSilentFailed 호출됨 (settled=false → timer 만료 분기). 첫 401에서
    // silent SSO 재시도 흐름이 들어왔는지 fetch call count로 검증.
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 401 }));
    saveAuth("t", SAMPLE_USER);
    const stale = String(Date.now() - 5 * 60 * 1000 - 1000);
    sessionStorage.setItem("dy_silent_failed", stale);

    await authFetch("/api/test");

    // stale 상태에선 silent SSO를 trigger (iframe timeout 후 markSilentFailed) →
    // sessionStorage 값이 새 timestamp marker로 교체됨
    const raw = sessionStorage.getItem("dy_silent_failed");
    expect(raw).not.toBe(stale);
    expect(raw).not.toBeNull();
    fetchSpy.mockRestore();
  }, 10_000);
});

/**
 * PR-CY (INCIDENT #1 #4) — verifyAndHydrateFromMe.
 *
 * callback page에서 normal SSO 성공 후 redirect 직전 1회 호출.
 * - 200: 응답 user로 saveAuth 갱신 (fragment schema 변경 / chunk stale 자동 정정).
 * - 401: graceful fallback — null 반환, console.warn, saveAuth 호출 X.
 * - network: 동일 fallback.
 *
 * authFetch 사용 X — 401 시 silent SSO trigger → callback 무한 재귀(INCIDENT #4) 회피.
 */
describe("verifyAndHydrateFromMe (PR-CY)", () => {
  it("200 → 응답 user로 saveAuth 갱신 + user 반환", async () => {
    const responseUser: UserInfo = { ...SAMPLE_USER, name: "갱신된이름" };
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify(responseUser), { status: 200 }),
      );

    const result = await verifyAndHydrateFromMe();
    expect(result).toEqual(responseUser);
    expect(getUser()).toEqual(responseUser); // saveAuth로 저장됨
    fetchSpy.mockRestore();
  });

  it("401 → null 반환 + saveAuth 호출 X + console.warn", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("Unauthorized", { status: 401 }));

    const result = await verifyAndHydrateFromMe();
    expect(result).toBeNull();
    expect(getUser()).toBeNull(); // saveAuth 호출 X
    expect(warnSpy).toHaveBeenCalled();
    fetchSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("network reject → null + console.warn (fragment fallback 흐름)", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new TypeError("Network error"));

    const result = await verifyAndHydrateFromMe();
    expect(result).toBeNull();
    expect(getUser()).toBeNull();
    expect(warnSpy).toHaveBeenCalled();
    fetchSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
