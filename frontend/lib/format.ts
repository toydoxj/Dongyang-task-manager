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
