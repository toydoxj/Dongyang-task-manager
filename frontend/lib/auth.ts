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

export function saveAuth(token: string, user: UserInfo): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("dy_logged_out");
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

/** 인증 헤더가 자동 포함된 fetch 래퍼 — 401 시 자동 로그아웃. */
export async function authFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, { ...init, headers });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
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
 * 결과를 callback 페이지가 postMessage로 부모(여기)에 전달. timeout 8초.
 */
export function trySilentSSO(next: string = "/"): Promise<UserInfo | null> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") return resolve(null);
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
      // origin 검증 — backend가 frontend origin으로 redirect하므로 같은 origin
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
        cleanup();
        resolve(null);
      }
    };
    window.addEventListener("message", onMessage);

    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        cleanup();
        resolve(null);
      }
    }, 8000);

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
