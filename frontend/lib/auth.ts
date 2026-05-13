import { API_BASE, AuthStatus, UserInfo } from "./types";

const TOKEN_KEY = "dy_auth_token";  // PR-BI: legacy localStorage key — clearAuth에서만 정리용
const USER_KEY = "dy_auth_user";

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

/** PR-BI (Phase 4-G 2단계): web은 cookie 단독 인증으로 전환 — token은 saveAuth에서
 * 더 이상 저장하지 않는다. user info만 localStorage에 둠 (UI 표시용). 인증 자체는
 * httpOnly cookie. dy-midas는 별도 client로 header(Bearer) 그대로 사용. */
export function saveAuth(user: UserInfo): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("dy_logged_out");
    window.sessionStorage.removeItem(SILENT_FAILED_KEY);
  }
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);  // 1단계 잔존 token 정리
  localStorage.removeItem(USER_KEY);
  // logout 직후 silent SSO 자동 재로그인 방지 (현재 탭 한정)
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem("dy_logged_out", "1");
  }
}

export function isLoggedIn(): boolean {
  // PR-BI: cookie는 httpOnly라 JS에서 못 읽음 → user info 존재로 추정 판단.
  // cookie가 만료/삭제됐어도 user는 남아있을 수 있으나, 첫 fetch에서 401 → clearAuth + redirect.
  return !!getUser();
}

/** 인증된 fetch 래퍼 — 401 시 자동 로그아웃.
 *
 * PR-BI (Phase 4-G 2단계): credentials:"include"만으로 httpOnly cookie 자동 첨부.
 * Authorization header 첨부는 제거 — web은 cookie 단독 인증.
 */
export async function authFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, { ...init, credentials: "include" });
  if (res.status === 401) {
    clearAuth();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
}

/** PR-BH: backend logout — httpOnly cookie 제거 + DB UserSession 삭제. cookie가
 * 자동 첨부되므로 별도 인증 헤더 불필요. */
export async function backendLogout(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
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
        // PR-BI: token은 무시 — backend가 silent callback redirect에서 cookie도 set함.
        saveAuth(data.user);
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

/** fragment(`#token=...&user=<base64>`)에서 user 정보를 꺼내 저장. 호출 후 fragment 정리.
 *
 * PR-BI: token은 fragment에 여전히 포함되지만 frontend는 무시 (인증은 cookie). 호환을
 * 위해 backend는 한동안 token도 fragment에 보낸다. 추후 backend에서 fragment token 제거.
 */
export function consumeCallbackFragment(): {
  user: UserInfo;
  next: string;
} | null {
  if (typeof window === "undefined") return null;
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const userB64 = params.get("user");
  const next = params.get("next") || "/";
  if (!userB64) return null;
  try {
    const user = JSON.parse(decodeBase64UrlUtf8(userB64)) as UserInfo;
    saveAuth(user);
    // fragment 즉시 제거 (브라우저 history 노출 회피 — token도 함께 제거)
    window.history.replaceState(null, "", window.location.pathname);
    return { user, next };
  } catch {
    return null;
  }
}
