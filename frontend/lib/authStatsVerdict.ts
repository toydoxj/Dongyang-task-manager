// PR-EZ: admin/auth-stats verdict 함수 — page에서 분리하여 vitest로 boundary 검증.
// 임계값 변경 시 자동 검출 + 운영자 매뉴얼(USER_MANUAL 9.5)과 일관성 보장.

export const GO_THRESHOLD = 0.99;
export const WATCH_THRESHOLD = 0.95;

export type VerdictTone = "go" | "watch" | "no-go" | "idle";

export interface VerdictMeta {
  label: string;
  tone: VerdictTone;
  detail: string;
}

/** cookie-only 준비율과 표본 수로 5차 재시도 verdict 산출.
 * - total === 0 → idle (데이터 없음)
 * - ratio ≥ 0.99 → go
 * - 0.95 ≤ ratio < 0.99 → watch
 * - ratio < 0.95 → no-go
 */
export function verdictForRatio(ratio: number, total: number): VerdictMeta {
  if (total === 0) {
    return {
      label: "데이터 없음",
      tone: "idle",
      detail: "아직 인증 호출이 누적되지 않았습니다. 사용자 활동 후 다시 확인.",
    };
  }
  if (ratio >= GO_THRESHOLD) {
    return {
      label: "GO — 5차 재시도 안전",
      tone: "go",
      detail: `cookie-only 준비율 ${(ratio * 100).toFixed(2)}% ≥ ${(GO_THRESHOLD * 100).toFixed(0)}% 임계 초과.`,
    };
  }
  if (ratio >= WATCH_THRESHOLD) {
    return {
      label: "관찰 지속",
      tone: "watch",
      detail: `cookie-only 준비율 ${(ratio * 100).toFixed(2)}% — 95% 도달, 99% 수렴 대기.`,
    };
  }
  return {
    label: "NO-GO — cookie-only 차단 요청 잔존",
    tone: "no-go",
    detail: `cookie-only 준비율 ${(ratio * 100).toFixed(2)}% < ${(WATCH_THRESHOLD * 100).toFixed(0)}%. PR-EM/EN 재시도 시 회귀 위험.`,
  };
}
