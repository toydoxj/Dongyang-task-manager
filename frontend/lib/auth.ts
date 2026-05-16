import { API_BASE, AuthStatus, UserInfo } from "./types";

const TOKEN_KEY = "dy_auth_token";
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

// PR-BN (INCIDENT 체크리스트 #2): backward-compatible signature.
// PR-EM (Phase 4-G 2단계): saveAuth(token, user)도 token 인자를 무시 — cookie가
// 인증 source. signature는 backward-compat 유지 (Vercel chunk 부분 stale로 옛/새
// chunk 혼재 시 type mismatch 예방). PR-BI 사고(saveAuth signature 변경 + chunk
// stale → user 자리에 token 저장 → getUser()=null → 로그인 loop) 회피.
// 기존 사용자 localStorage token은 backend가 header fallback으로 받아주므로
// 점진 마이그레이션 — clearAuth 또는 새 로그인부터 cookie 단독으로 수렴.
export function saveAuth(token: string, user: UserInfo): void;
export function saveAuth(user: UserInfo): void;
export function saveAuth(arg1: string | UserInfo, user?: UserInfo): void {
  let resolvedUser: UserInfo;
  if (typeof arg1 === "string" && user !== undefined) {
    resolvedUser = user;
  } else if (typeof arg1 === "object" && arg1 !== null) {
    resolvedUser = arg1 as UserInfo;
  } else {
    return; // 잘못된 호출 — silent skip (e.g. arg1=undefined)
  }
  // PR-EM: token 인자 무시 — XSS 영향 줄임. cookie가 인증 source.
  localStorage.setItem(USER_KEY, JSON.stringify(resolvedUser));
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem("dy_logged_out");
    window.sessionStorage.removeItem(SILENT_FAILED_KEY);
  }
}

export function clearAuth(): void {
  // PR-EN: TOKEN_KEY는 더 이상 저장하지 않지만 PR-EM 이전 사용자의 legacy
  // localStorage 토큰 cleanup을 위해 removeItem은 유지 (idempotent).
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  // logout 직후 silent SSO 자동 재로그인 방지 (현재 탭 한정)
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem("dy_logged_out", "1");
  }
}

// PR-EM (Phase 4-G 2단계): cookie httpOnly이라 frontend가 직접 read 불가 → 대신
// localStorage의 user JSON 존재 여부로 판단. cookie가 만료된 경우 stale user는
// AuthGuard 부팅 시 verifyAndHydrateFromMe()로 검증되어 401이면 silent SSO 또는
// login redirect로 회복.
export function isLoggedIn(): boolean {
  return !!getUser();
}

/** 인증 fetch 래퍼 — 401 시 silent SSO 1회 재시도 후 로그아웃.
 *
 * PR-BH (Phase 4-G 1단계): credentials:"include" — httpOnly JWT cookie 자동 첨부.
 * PR-BO (INCIDENT #3): 401 발생 시 silent SSO 1회 재시도. cookie 만료로 인한
 * 일시 회복 가능. 실패 시 clearAuth + /login. 무한 재귀 방지 위해 retry flag.
 * PR-EN (Phase 4-G 2단계 3차): Authorization header 첨부 코드 제거 — cookie 단독
 * 인증. backend는 여전히 header fallback 받지만 더 이상 frontend가 보내지 않음.
 */
export async function authFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  return _authFetchInternal(path, init, false);
}

async function _authFetchInternal(
  path: string,
  init: RequestInit | undefined,
  retried: boolean,
): Promise<Response> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const res = await fetch(url, { ...init, credentials: "include" });

  if (res.status !== 401) return res;

  // PR-DV (INCIDENT #5 체크리스트 #3): 인증 검증 endpoint는 401에 silent SSO를
  // trigger하면 안 됨. silent SSO 자체가 callback page를 사용하므로 callback에서
  // /api/auth/me 같은 검증 endpoint를 trigger하면 무한 재귀 위험.
  // 현재는 callsite가 없지만 미래 회귀 방지 예방.
  const isAuthVerifyEndpoint =
    path.startsWith("/api/auth/me") || path.startsWith("/api/auth/status");

  // 401. 첫 발생이면 silent SSO 한 번 시도해 cookie/token 갱신 후 재시도.
  // 같은 탭에서 silent 5분 안에 실패했거나 명시 logout 직후면 skip.
  // PR-CX: TTL 기반 — 5분 후 재시도 허용 (기존 영구 차단 → cookie 회복 가능).
  if (!retried && !isAuthVerifyEndpoint && typeof window !== "undefined") {
    const justLoggedOut = window.sessionStorage.getItem("dy_logged_out") === "1";
    if (!justLoggedOut && !_isSilentFailedRecently()) {
      const recoveredUser = await trySilentSSO(window.location.pathname || "/");
      if (recoveredUser) {
        return _authFetchInternal(path, init, true);
      }
    }
  }

  // silent SSO 미시도 / 실패 / 재시도도 401 → 정리
  clearAuth();
  if (typeof window !== "undefined") window.location.href = "/login";
  return res;
}

/** PR-BH: backend logout — httpOnly cookie 제거 + DB UserSession 삭제. 실패해도
 * 로컬 clearAuth는 호출자가 별도로 진행하므로 본 함수는 best-effort.
 * PR-EN: Authorization header 첨부 제거 — cookie 단독으로 backend가 user 식별. */
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
// PR-CX (INCIDENT #1 체크리스트 #3 보강): silent_failed flag를 timestamp로 저장해
// 5분 후 자동 재시도 가능. 기존엔 같은 탭에서 한 번 실패하면 영구 차단되어
// cookie 만료 후 사용자가 회복 불가 (새로고침 안 하면 loop).
const SILENT_FAIL_TTL_MS = 5 * 60 * 1000;


function _markSilentFailed(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(SILENT_FAILED_KEY, String(Date.now()));
}


function _isSilentFailedRecently(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.sessionStorage.getItem(SILENT_FAILED_KEY);
  if (!raw) return false;
  // legacy: "1" 그대로면 fresh fail로 간주해 5분 TTL 적용
  const at = Number(raw);
  if (!Number.isFinite(at) || at === 1) {
    _markSilentFailed();
    return true;
  }
  return Date.now() - at < SILENT_FAIL_TTL_MS;
}

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
        _markSilentFailed();
        cleanup();
        resolve(null);
      }
    };
    window.addEventListener("message", onMessage);

    const timer = window.setTimeout(() => {
      if (!settled) {
        settled = true;
        // X-Frame-Options 차단·NAVER prompt=none 미지원 등 → 같은 탭에서 재시도 안 함
        _markSilentFailed();
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

/** PR-CY (INCIDENT #1 #4): cookie 기반 /me fetch로 user/cookie validity 동시 검증.
 *
 * 사용처: callback page에서 normal SSO 성공 후 redirect 직전 1회 호출.
 * - 200: 응답 user로 saveAuth 갱신 (fragment user_b64 schema 변경 / chunk stale 자동 정정).
 * - 401/network: graceful fallback — fragment user 그대로 사용 + console.warn (운영 진단).
 *
 * authFetch 사용 X — 401 시 silent SSO trigger → callback 무한 재귀(INCIDENT #4) 회피.
 * 직접 fetch + credentials:"include"로 cookie만 검증.
 */
export async function verifyAndHydrateFromMe(): Promise<UserInfo | null> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/me`, {
      credentials: "include",
    });
    if (res.status === 401) {
      // cookie 발급 실패 가능성 — 운영 진단용 log만 남기고 fragment user 신뢰
      console.warn("[auth] /me 401 — cookie 미발급/만료. fragment user fallback");
      return null;
    }
    if (!res.ok) {
      console.warn(`[auth] /me ${res.status} — fragment user fallback`);
      return null;
    }
    const user = (await res.json()) as UserInfo;
    // saveAuth(user) 1-arg form — token 위치는 cookie. backward-compat overload OK.
    saveAuth(user);
    return user;
  } catch (e) {
    console.warn("[auth] /me network fail — fragment user fallback:", e);
    return null;
  }
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
