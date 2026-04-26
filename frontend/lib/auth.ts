import { API_BASE, AuthStatus, TokenResponse, UserInfo } from "./types";

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

async function postAuth(
  path: "/api/auth/login" | "/api/auth/register",
  body: Record<string, string>,
): Promise<TokenResponse> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const d = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(d.detail ?? `요청 실패 (${res.status})`);
  }
  const data = (await res.json()) as TokenResponse;
  saveAuth(data.access_token, data.user);
  return data;
}

export function login(username: string, password: string): Promise<TokenResponse> {
  return postAuth("/api/auth/login", { username, password });
}

export function register(
  username: string,
  password: string,
  name: string,
  email: string,
): Promise<TokenResponse> {
  return postAuth("/api/auth/register", { username, password, name, email });
}

export async function requestJoin(
  username: string,
  password: string,
  name: string,
  email: string,
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/auth/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, name, email }),
  });
  if (!res.ok) {
    const d = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(d.detail ?? `요청 실패 (${res.status})`);
  }
  return (await res.json()) as { status: string; message: string };
}
