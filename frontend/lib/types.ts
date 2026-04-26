export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

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
