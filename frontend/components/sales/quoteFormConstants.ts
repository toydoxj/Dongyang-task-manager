/**
 * QuoteForm 도메인 상수.
 * PR-AN — components/sales/QuoteForm.tsx에서 추출.
 *
 * 단가 등급 default — backend `_resolve_rate`의 default_grade와 일치.
 * 견적서 양식의 N/O열 옵션 — xlsx 실제 옵션 그대로.
 */

import type { EngineerGrade } from "@/lib/domain";

// 견적서 종류별 default 단가 등급 — backend _resolve_rate의 default_grade와 일치.
// 사용자가 등급 select에서 미선택(null) 시 표시 안내값.
export const DEFAULT_ENGINEER_GRADE: Record<string, EngineerGrade> = {
  구조감리: "기술사",
  "3자검토": "특급기술자",
  // 그 외 모든 종류는 고급기술자
};

export const defaultGradeFor = (qt: string): EngineerGrade =>
  DEFAULT_ENGINEER_GRADE[qt] ?? "고급기술자";

// 견적서 양식의 N/O열 옵션 — xlsx 실제 옵션과 일치
export const STRUCTURE_FORMS = [
  "철근콘크리트구조",
  "철근콘크리트조(벽식구조)",
  "철근콘크리트구조 + 철골구조",
  "강구조(철골구조)",
  "하중전이구조",
  "PC구조, 복합구조",
  "플랜트구조",
  "특수구조",
];

export const TYPE_RATES = [0.8, 0.9, 1.0, 1.1, 1.2];
export const STRUCTURE_RATES = [0.5, 1.0, 1.2, 1.25, 1.5];

export const COEFFICIENTS = [
  { value: 0.5, label: "0.5 (구조계산서만)" },
  { value: 1.0, label: "1.0 (계산서+도면)" },
];
