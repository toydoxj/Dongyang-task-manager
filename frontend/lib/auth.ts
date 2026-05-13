import { API_BASE, AuthStatus, UserInfo } from "./types";

const TOKEN_KEY = "dy_auth_token";
const USER_KEY = "dy_auth_user";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): UserInfo | null {
  if (typeof window === "undefined") return null;
  const s = localStorage.getItem(USER_KEY);
  if (!s) return null;
  try {
    return JSON.parse(s) as UserInfo;
  } catch {
    return null;
  }
}

// PR-BN (INCIDENT 체크리스트 #2): backward-compatible signature.
// 1단계(현재): saveAuth(token, user) — token + user 모두 localStorage 저장.
// 2단계(추후): saveAuth(user) — token 인자 없이 user만. cookie가 인증 source.
// 두 호출 모두 안전 — Vercel chunk 부분 stale로 옛/새 chunk 혼재 시 type mismatch
// 예방. PR-BI 사고(saveAuth signature 변경 + chunk stale → user 자리에 token 저장
// → getUser()=null → 로그인 loop) 회피.
export function saveAuth(token: string, user: UserInfo): void;
export function saveAuth(user: UserInfo): void;
export function saveAuth(arg1: string | UserInfo, user?: UserInfo): void {
  let resolvedUser: UserInfo;
  let token: string | null = null;
  if (typeof arg1 === "string" && user !== undefined) {
    token = arg1;
    resolvedUser = user;
  } else if (typeof arg1 === "object" && arg1 !== null) {
    resolvedUser = arg1 as UserInfo;
  } else {
    return; // 잘못된 호출 — silent skip (e.g. arg1=undefined)
  }
  if (token !== null) {
    localStorage.setItem(TOKEN_KEY, token);
  }
  localStorage.setItem(USER_KEY, JSON.stringify(resolvedUser));
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("dy_logged_out");
    window.sessionStorage.removeItem(SILENT_FAILED_KEY);
  }
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  // logout 직후 silent SSO 자동 재로그인 방지 (현재 탭 한정)
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem("dy_logged_out", "1");
  }
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

/** 인증 헤더가 자동 포함된 fetch 래퍼 — 401 시 자동 로그아웃.
 *
 * PR-BH (Phase 4-G 1단계): credentials:"include" 추가 — 운영(.dyce.kr 공유 cookie)에서
 * httpOnly JWT cookie가 cross-origin 요청에 자동 첨부되도록. localStorage token도
 * 그대로 유지(점진 마이그레이션 — 두 채널 모두 지원). 2단계에서 header 제거 예정.
 */
export async function authFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, { ...init, credentials: "include", headers });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
}

/** PR-BH: backend logout — httpOnly cookie 제거 + DB UserSession 삭제. 실패해도
 * 로컬 clearAuth는 호출자가 별도로 진행하므로 본 함수는 best-effort. */
export async function backendLogout(): Promise<void> {
  try {
    const headers = new Headers();
    const t = getToken();
    if (t) headers.set("Authorization", `Bearer ${t}`);
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers,
    });
  } catch {
    /* network down 등은 무시 — 사용자 인지 logout flow는 차단 안 함 */
  }
}

export async function checkAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${API_BASE}/api/auth/status`);
  return (await res.json()) as AuthStatus;
}

// ── NAVER WORKS OIDC SSO ──

export function worksLoginUrl(next: string = "/"): string {
  const qs = new URLSearchParams({ next }).toString();
  return `${API_BASE}/api/auth/works/login?${qs}`;
}

/** silent SSO (prompt=none) 시도. NAVER 세션 살아있으면 silent 토큰 발급, 없으면 실패.
 * 결과를 callback 페이지가 postMessage로 부모(여기)에 전달. timeout 3초.
 *
 * NAVER가 prompt=none을 거부하거나 X-Frame-Options로 iframe 차단 시 timeout으로 빠짐.
 * fail 후 같은 탭에서 재시도 안 하도록 sessionStorage('dy_silent_failed')에 표시.
 */
const SILENT_FAILED_KEY = "dy_silent_failed";
const SILENT_TIMEOUT_MS = 3000;

export function trySilentSSO(next: string = "/"): Promise<UserInfo | null> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") return resolve(null);
    // 같은 탭에서 한 번 실패했으면 즉시 skip
    if (window.sessionStorage.getItem(SILENT_FAILED_KEY) === "1") {
      return resolve(null);
    }
    const iframe = document.createElement("iframe");
    iframe.style.display = "none";
    iframe.src = `${API_BASE}/api/auth/works/login?silent=1&next=${encodeURIComponent(next)}`;

    let settled = false;
    const cleanup = (): void => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(timer);
      if (iframe.parentNode) document.body.removeChild(iframe);
    };

    const onMessage = (e: MessageEvent): void => {
      if (settled) return;
      if (e.origin !== window.location.origin) return;
      const data = e.data as
        | { type: "sso_silent_success"; token: string; user: UserInfo }
        | { type: "sso_silent_failed"; reason?: string }
        | undefined;
      if (!data || typeof data !== "object") return;
      if (data.type === "sso_silent_success") {
        settled = true;
        saveAuth(data.token, data.user);
        cleanup();
        resolve(data.user);
      } else if (data.type === "sso_silent_failed") {
        settled = true;
        window.sessionStorage.setItem(SILENT_FAILED_KEY, "1");
        cleanup();
        resolve(null);
      }
    };
    window.addEventListener("message", onMessage);

    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        // X-Frame-Options 차단·NAVER prompt=none 미지원 등 → 같은 탭에서 재시도 안 함
        window.sessionStorage.setItem(SILENT_FAILED_KEY, "1");
        cleanup();
        resolve(null);
      }
    }, SILENT_TIMEOUT_MS);

    document.body.appendChild(iframe);
  });
}

function decodeBase64UrlUtf8(s: string): string {
  let b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder("utf-8").decode(bytes);
}

/** fragment(`#token=...&user=<base64>`)에서 인증 정보를 꺼내 저장. 호출 후 fragment 정리. */
export function consumeCallbackFragment(): {
  token: string;
  user: UserInfo;
  next: string;
} | null {
  if (typeof window === "undefined") return null;
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const token = params.get("token");
  const userB64 = params.get("user");
  const next = params.get("next") || "/";
  if (!token || !userB64) return null;
  try {
    const user = JSON.parse(decodeBase64UrlUtf8(userB64)) as UserInfo;
    saveAuth(token, user);
    // fragment 즉시 제거 (브라우저 history 노출 회피)
    window.history.replaceState(null, "", window.location.pathname);
    return { token, user, next };
  } catch {
    return null;
  }
}
