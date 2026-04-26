// 한국어 표기 포맷 헬퍼.

export function formatWon(amount: number | null | undefined, abbreviated = false): string {
  if (amount == null) return "—";
  if (abbreviated) {
    if (amount >= 1e8) return `${(amount / 1e8).toFixed(1)}억`;
    if (amount >= 1e4) return `${(amount / 1e4).toFixed(0)}만`;
  }
  return `${amount.toLocaleString("ko-KR")}원`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  // YYYY-MM-DD 부분만 (timezone 제거)
  return iso.slice(0, 10).replace(/-/g, ".");
}

/** ISO datetime → 한국 시간 (YYYY.MM.DD HH:mm) */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const fmt = new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  });
  // ko-KR 출력: "2026. 04. 27. 09:30" → 정리
  return fmt
    .format(d)
    .replace(/\.\s/g, ".")
    .replace(/\.(\d{2}:)/, " $1");
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${Math.round(value * 100)}%`;
}

/** 두 ISO 날짜 사이 일수 (양수면 future). */
export function daysFromNow(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(iso).getTime();
  const now = Date.now();
  return Math.floor((target - now) / (1000 * 60 * 60 * 24));
}

export function dDayLabel(iso: string | null | undefined): string {
  const d = daysFromNow(iso);
  if (d == null) return "";
  if (d === 0) return "D-Day";
  if (d > 0) return `D-${d}`;
  return `D+${-d}`;
}
