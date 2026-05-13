import { describe, expect, it } from "vitest";

import { CTA } from "./cta";

/**
 * CTA 상수는 UI 일관성 보장용 (COMMON-003) — 정확한 표기 유지가 회귀 방지.
 * 라벨이 바뀌면 PriorityActionsPanel / Kanban 등 다수 호출처도 함께 검토 필요.
 */
describe("CTA 상수", () => {
  it("8개 표준 라벨이 모두 정의됨", () => {
    expect(CTA.detail).toBeDefined();
    expect(CTA.openProject).toBeDefined();
    expect(CTA.viewTasks).toBeDefined();
    expect(CTA.viewSeals).toBeDefined();
    expect(CTA.viewIncomes).toBeDefined();
    expect(CTA.viewMyTasks).toBeDefined();
    expect(CTA.viewLoad).toBeDefined();
    expect(CTA.viewSource).toBeDefined();
  });

  it("모든 라벨이 비어있지 않음", () => {
    for (const [key, value] of Object.entries(CTA)) {
      expect(value, `${key} must not be empty`).toBeTruthy();
    }
  });
});
