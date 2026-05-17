// /api/auth/channel-stats — PR-ES (Phase 4-G 5차 모니터링).
// admin only. backend in-memory 누적 카운터 — Render restart 시 reset.
import { authFetch, jsonOrThrow } from "./_internal";

export interface AuthChannelStats {
  header: number;
  cookie: number;
  total: number;
  cookie_ratio: number; // 0..1
  since: string; // ISO
}

export async function getAuthChannelStats(): Promise<AuthChannelStats> {
  const res = await authFetch(`/api/auth/channel-stats`);
  return jsonOrThrow<AuthChannelStats>(res);
}
