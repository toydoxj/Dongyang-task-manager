// /api/auth/channel-stats — PR-ES (Phase 4-G 5차 모니터링).
// admin only. backend in-memory 누적 카운터 — Render restart 시 reset.
import { authFetch, jsonOrThrow } from "./_internal";

export interface AuthChannelStats {
  header: number;
  cookie: number;
  total: number;
  cookie_ratio: number; // 0..1
  header_with_valid_cookie?: number;
  header_without_cookie?: number;
  header_with_invalid_cookie?: number;
  header_with_mismatched_cookie?: number;
  cookie_ready?: number;
  cookie_blocked?: number;
  cookie_readiness_total?: number;
  cookie_ready_ratio?: number; // 0..1
  since: string; // ISO
}

export async function getAuthChannelStats(): Promise<AuthChannelStats> {
  const res = await authFetch(`/api/auth/channel-stats`);
  return jsonOrThrow<AuthChannelStats>(res);
}
