/**
 * COMMON-003 — 공통 CTA 문구 표준.
 *
 * UX 일관성을 위해 모든 list/카드/액션 패널의 button·link 라벨은
 * 이 상수에서 가져옴. 새 항목이 필요하면 여기에 먼저 추가하고 사용처에 import.
 *
 * 원칙:
 * - 동사 + 목적어 형태 ("XX 보기" / "XX 열기")
 * - "관리"·"편집"·"수정" 같은 admin 어휘는 별도 (여기 X — 메뉴/페이지 헤더에서 사용)
 * - 카드 전체가 link인 경우(ProjectCard·MyProjectSnapshots 등)는 별도 라벨 없이 카드 자체가 CTA
 */
export const CTA = {
  /** 상세 페이지로 이동 (project / sale / seal 공통 fallback) */
  detail: "상세 보기",
  /** 프로젝트 list 또는 단일 프로젝트로 이동 */
  openProject: "프로젝트 열기",
  /** 프로젝트 안 TASK 칸반 또는 관련 TASK */
  viewTasks: "관련 TASK 보기",
  /** 날인요청 list 또는 상세 */
  viewSeals: "날인 보기",
  /** 수금/매출 list */
  viewIncomes: "관련 매출 보기",
  /** 본인 업무 화면 */
  viewMyTasks: "내 업무에서 처리",
  /** 팀별/직원별 부하 화면 */
  viewLoad: "팀별 부하 보기",
  /** 노션 등 원본 데이터 source link */
  viewSource: "원본 데이터 보기",
} as const;

export type CTAKey = keyof typeof CTA;
