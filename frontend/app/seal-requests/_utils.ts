/**
 * /seal-requests 페이지 helpers + constants.
 * PR-AZ — page.tsx에서 추출.
 */

export const STATUS_TABS = ["전체", "1차검토 중", "2차검토 중", "승인", "반려"] as const;
export type StatusTab = (typeof STATUS_TABS)[number];

export const STATUS_COLOR: Record<string, string> = {
  "1차검토 중": "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400",
  "2차검토 중": "bg-blue-500/15 text-blue-700 dark:text-blue-400",
  승인: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  반려: "bg-red-500/15 text-red-700 dark:text-red-400",
};

/** Drive share URL의 query string에서 resourceKey(폴더 fileId) 추출. */
export function extractResourceKey(url: string): string {
  if (!url) return "";
  try {
    const u = new URL(url);
    return u.searchParams.get("resourceKey") ?? "";
  } catch {
    return "";
  }
}

export function resolveClientName(
  id: string,
  clients: { id: string; name: string }[] | undefined,
): string {
  if (!id || !clients) return id;
  return clients.find((c) => c.id === id)?.name ?? id;
}
