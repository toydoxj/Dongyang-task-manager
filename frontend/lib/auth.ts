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
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
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
