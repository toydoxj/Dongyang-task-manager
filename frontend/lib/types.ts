/**
 * 백엔드 API 베이스 URL.
 *
 * - dev (next dev): NEXT_PUBLIC_API_BASE 환경변수 사용 (기본 http://127.0.0.1:8000)
 * - packaged Electron: backend.exe가 정적 frontend 도 서빙 → 같은 origin 사용
 *   (backend port는 랜덤이므로 빌드 시점에 8000을 inline 하면 안 됨)
 */
function resolveApiBase(): string {
  if (typeof window !== "undefined") {
    // Electron이 명시 주입한 경우
    const fromWindow = (window as unknown as { __BACKEND_URL__?: string }).__BACKEND_URL__;
    if (fromWindow) return fromWindow;
    // http(s) origin 이면 같은 origin 사용 (packaged 모드)
    const proto = window.location.protocol;
    if (proto === "http:" || proto === "https:") {
      return window.location.origin;
    }
  }
  // SSR/빌드 시점 또는 file:// fallback
  return process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";
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
