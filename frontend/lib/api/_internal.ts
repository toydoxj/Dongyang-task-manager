// 도메인 파일들이 공유하는 fetch/QS helper. lib/api.ts에서 private이던 것을 export.

import { authFetch } from "@/lib/auth";

export async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res
      .json()
      .then((d) => (d as { detail?: string }).detail)
      .catch(() => undefined);
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export function qs(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export { authFetch };

/** PDF 다운로드 helper — Content-Disposition filename*에서 한글 파일명 자동 추출.
 * sales/weekly 등 PDF endpoint 호출자가 공유. */
export async function downloadPdfBlob(
  url: string,
  fallbackFilename: string,
): Promise<void> {
  const res = await authFetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      (detail as { detail?: string } | null)?.detail ??
        `${res.status} ${res.statusText}`,
    );
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  let filename = fallbackFilename;
  const star = cd.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try {
      filename = decodeURIComponent(star[1]);
    } catch {
      /* fallthrough */
    }
  }
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}
