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

export interface SyncRunLogItem {
  run_id: string;
  source: string;
  kind: string | null;
  full: boolean;
  status: string;
  started_at: string;
  finished_at: string | null;
  elapsed_seconds: number | null;
  result: string;
  error: string;
}

export interface SyncRunLogResponse {
  items: SyncRunLogItem[];
}

export interface OutboxStatusEntry {
  status: string;
  count: number;
  oldest_created_at: string | null;
}

export interface OutboxStatusResponse {
  items: OutboxStatusEntry[];
}

export interface OutboxDrainResponse {
  status: string;
  batch: number;
  run_id: string | null;
}

export async function adminSyncStatus(): Promise<SyncStatusResponse> {
  const res = await authFetch(`/api/admin/sync/status`);
  return jsonOrThrow<SyncStatusResponse>(res);
}

export async function adminSyncRuns(
  limit: number = 10,
): Promise<SyncRunLogResponse> {
  const res = await authFetch(`/api/admin/sync/runs?limit=${limit}`);
  return jsonOrThrow<SyncRunLogResponse>(res);
}

export interface SyncRunResponse {
  status: string; // "started" | "already_running"
  kind: string | null;
  full: boolean;
  run_id: string;
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

export async function adminOutboxStatus(): Promise<OutboxStatusResponse> {
  const res = await authFetch(`/api/admin/sync/outbox`);
  return jsonOrThrow<OutboxStatusResponse>(res);
}

export async function adminOutboxDrain(
  batch: number = 20,
): Promise<OutboxDrainResponse> {
  const res = await authFetch(`/api/admin/sync/outbox/drain?batch=${batch}`, {
    method: "POST",
  });
  return jsonOrThrow<OutboxDrainResponse>(res);
}
