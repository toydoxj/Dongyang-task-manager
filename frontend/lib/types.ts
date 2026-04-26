/**
 * 백엔드 API 베이스 URL — 빌드 시점에 inline된 NEXT_PUBLIC_API_BASE 사용.
 * - Vercel 운영: https://api.dyce.kr
 * - 로컬 dev:   http://127.0.0.1:8000 (.env.local에서 설정)
 */
function resolveApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
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
  last_login_at: string | null;
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

