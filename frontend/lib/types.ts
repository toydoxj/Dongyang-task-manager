/**
 * 백엔드 API 베이스 URL 결정 우선순위:
 *  1) Electron이 런타임 주입한 window.__BACKEND_URL__
 *  2) 빌드 시점에 inline된 NEXT_PUBLIC_API_BASE (dev: .env.local의 :8000)
 *  3) window.location.origin (packaged: backend가 frontend 정적 서빙)
 *  4) http://127.0.0.1:8000 (SSR/file:// fallback)
 *
 * NOTE: packaged 빌드는 next.config.ts의 env override로
 *       NEXT_PUBLIC_API_BASE="" 가 inline 되어 (3)이 동작한다.
 */
function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const injected = (window as unknown as { __BACKEND_URL__?: string })
      .__BACKEND_URL__;
    if (injected) return injected;
  }
  const envBase = process.env.NEXT_PUBLIC_API_BASE;
  if (envBase) return envBase;
  if (typeof window !== "undefined") {
    const proto = window.location.protocol;
    if (proto === "http:" || proto === "https:") {
      return window.location.origin;
    }
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE: string = resolveApiBase();

export interface UserInfo {
  id: number;
  username: string;
  name: string;
  email: string;
  role: "admin" | "user";
  status: "active" | "pending" | "rejected";
  notion_user_id: string;
}

export interface AuthStatus {
  initialized: boolean;
  user_count: number;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: UserInfo;
}

declare global {
  interface Window {
    electronAPI?: {
      isElectron: boolean;
      getVersion: () => Promise<string>;
    };
  }
}
