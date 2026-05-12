// /api/admin/sync — admin 강제 sync 트리거 + 마지막 상태
import { authFetch, jsonOrThrow } from "./_internal";

export interface SyncStatusItem {
  kind: string;
  last_incremental_synced_at: string | null;
  last_full_synced_at: string | null;
  last_error: string;
  last_run_count: number;
}

export interface SyncStatusResponse {
  items: SyncStatusItem[];
}

export async function adminSyncStatus(): Promise<SyncStatusResponse> {
  const res = await authFetch(`/api/admin/sync/status`);
  return jsonOrThrow<SyncStatusResponse>(res);
}

export interface SyncRunResponse {
  status: string; // "started" | "already_running"
  kind: string | null;
  full: boolean;
}

export async function adminSyncRun(
  body: { kind?: string; full?: boolean } = {},
): Promise<SyncRunResponse> {
  const res = await authFetch(`/api/admin/sync/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<SyncRunResponse>(res);
}
