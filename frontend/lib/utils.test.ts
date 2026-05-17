import { describe, expect, it } from "vitest";

import { cn } from "./utils";

/**
 * PR-FA: cn (clsx + tailwind-merge) 동작 검증.
 *
 * 컴포넌트 className 조합 표준 helper — clsx의 조건부 분기 + tailwind-merge의
 * 중복 클래스 정리(`p-2 p-4` → `p-4`). 회귀 시 UI 깨짐 위험.
 */
describe("cn (PR-FA)", () => {
  it("string 1개 → 그대로 반환", () => {
    expect(cn("text-sm")).toBe("text-sm");
  });

  it("string 여러 개 → 공백 join", () => {
    expect(cn("text-sm", "font-bold")).toBe("text-sm font-bold");
  });

  it("falsy(undefined/null/false) → skip", () => {
    expect(cn("text-sm", undefined, null, false, "font-bold")).toBe(
      "text-sm font-bold",
    );
  });

  it("조건부 객체 — true만 포함", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active");
  });

  it("배열 nested 평탄화", () => {
    expect(cn(["a", "b"], ["c"])).toBe("a b c");
  });

  it("tailwind-merge: 중복 padding 후순위 우선", () => {
    // p-2 p-4 → p-4 (마지막 padding이 이김)
    expect(cn("p-2 p-4")).toBe("p-4");
  });

  it("tailwind-merge: text 색상 중복 후순위 우선", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("tailwind-merge: 서로 다른 axis는 유지", () => {
    // padding과 margin은 별도 — 함께 유지
    const result = cn("p-4", "m-2");
    expect(result).toContain("p-4");
    expect(result).toContain("m-2");
  });

  it("빈 호출 → 빈 문자열", () => {
    expect(cn()).toBe("");
  });
});
