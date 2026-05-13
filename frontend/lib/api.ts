// 백엔드 API 호출 — 도메인별로 lib/api/{domain}.ts에 분리. 본 파일은 re-export hub.
//
// Phase 4-A 완료 (PR-S/S2 + PR-AR + PR-BD/BE/BG): 15 도메인 모두 lib/api/* 로 분리.
// 새 도메인 추가는 lib/api/{name}.ts 신설 + 본 파일에서 export *.

// ── 프로젝트 ── (PR-BE — lib/api/projects.ts)
export * from "./api/projects";

// ── 업무 TASK ── (Phase 4-A — lib/api/tasks.ts)
export * from "./api/tasks";

// ── Cashflow + 수금 CRUD ── (PR-BD — lib/api/cashflow.ts)
export * from "./api/cashflow";

// ── 협력업체(발주처) ── (PR-S — lib/api/clients.ts)
export * from "./api/clients";

// ── 계약 항목 ── (PR-BD — lib/api/contractItems.ts)
export * from "./api/contractItems";

// ── 마스터 프로젝트 + 이미지 CRUD ── (PR-BD — lib/api/masterProjects.ts)
export * from "./api/masterProjects";

// ── 사용자 관리 (admin) ── (PR-BD — lib/api/users.ts)
export * from "./api/users";

// ── 직원 명부 ── (PR-BD — lib/api/employees.ts)
export * from "./api/employees";

// ── WORKS Drive 임베디드 탐색기 ── (PR-BD — lib/api/drive.ts)
export * from "./api/drive";

// ── 건의사항 ── (PR-S2 — lib/api/suggestions.ts)
export * from "./api/suggestions";

// ── 날인요청 ── (PR-BE — lib/api/seals.ts)
export * from "./api/seals";

// ── 영업/견적 ── (PR-BG — lib/api/sales.ts)
export * from "./api/sales";

// ── 주간 업무일지 ── (PR-BG — lib/api/weekly.ts)
export * from "./api/weekly";

// ── 사내 공지 / 교육 일정 / 휴일 ── (PR-S2 — lib/api/notices.ts)
export * from "./api/notices";

// ── admin sync 트리거 + 상태 ── (PR-AR — lib/api/adminSync.ts)
export * from "./api/adminSync";

// ── 대시보드 집계 (PR-BJ Phase 4-F — lib/api/dashboard.ts)
export * from "./api/dashboard";
