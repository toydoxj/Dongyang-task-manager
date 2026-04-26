/**
 * 백엔드 API 베이스 URL 결정 우선순위:
 *  1) Electron 런타임 주입 window.__BACKEND_URL__ (Electron 빌드 부활 시)
 *  2) 빌드 시점 inline NEXT_PUBLIC_API_BASE (Vercel: https://api.dyce.kr / dev: http://127.0.0.1:8000)
 *  3) Electron packaged 빌드의 window.location.origin 폴백
 *  4) dev SSR fallback
 */
function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const injected = (window as unknown as { __BACKEND_URL__?: string })
      .__BACKEND_URL__;
    if (injected) return injected;
  }
  const envBase = process.env.NEXT_PUBLIC_API_BASE;
  if (envBase) return envBase;
  // Electron packaged 빌드(env가 빈 문자열로 inline)에서만 origin 사용
  if (typeof window !== "undefined") {
    const proto = window.location.protocol;
    if (proto === "file:" || proto === "app:") {
      return window.location.origin;
    }
  }
  return "http://127.0.0.1:8000";
}

export const API_BASE: string = resolveApiBase();

export type UserRole = "admin" | "team_lead" | "member";

export interface UserInfo {
  id: number;
  username: string;
  name: string;
  email: string;
  role: UserRole;
  status: "active" | "pending" | "rejected";
  notion_user_id: string;
}

export const ROLE_LABEL: Record<UserRole, string> = {
  admin: "관리자",
  team_lead: "팀장",
  member: "일반직원",
};

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
