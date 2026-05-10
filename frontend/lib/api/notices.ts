// 사내 공지 / 교육 일정 / 휴일 API (PR-W Phase 2.4).

import { authFetch } from "./_internal";

export type NoticeKind = "공지" | "교육" | "휴일";

export interface Notice {
  id: number;
  kind: NoticeKind;
  title: string;
  body: string;
  start_date: string; // YYYY-MM-DD
  end_date: string | null;
  author_user_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface NoticeListResponse {
  items: Notice[];
  count: number;
}

export interface NoticeCreateBody {
  kind: NoticeKind;
  title: string;
  body?: string;
  start_date: string;
  end_date?: string | null;
}

export interface NoticeUpdateBody {
  kind?: NoticeKind;
  title?: string;
  body?: string;
  start_date?: string;
  end_date?: string | null;
}

export async function listNotices(params?: {
  weekStart?: string;
  kind?: NoticeKind;
}): Promise<NoticeListResponse> {
  const qs = new URLSearchParams();
  if (params?.weekStart) qs.set("week_start", params.weekStart);
  if (params?.kind) qs.set("kind", params.kind);
  const url = `/api/notices${qs.toString() ? `?${qs.toString()}` : ""}`;
  const res = await authFetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as NoticeListResponse;
}

export async function createNotice(body: NoticeCreateBody): Promise<Notice> {
  const res = await authFetch("/api/notices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as Notice;
}

export async function updateNotice(
  id: number,
  body: NoticeUpdateBody,
): Promise<Notice> {
  const res = await authFetch(`/api/notices/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  return (await res.json()) as Notice;
}

export async function deleteNotice(id: number): Promise<void> {
  const res = await authFetch(`/api/notices/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
}
