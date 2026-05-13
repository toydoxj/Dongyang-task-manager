import { describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatWon } from "./format";

describe("formatWon", () => {
  it("null/undefined는 dash", () => {
    expect(formatWon(null)).toBe("—");
    expect(formatWon(undefined)).toBe("—");
  });

  it("기본 모드 — 쉼표 포함 원 표기", () => {
    expect(formatWon(0)).toBe("0원");
    expect(formatWon(1234567)).toBe("1,234,567원");
  });

  it("abbreviated — 1억 이상은 억, 1만 이상은 만", () => {
    expect(formatWon(100_000_000, true)).toBe("1.0억");
    expect(formatWon(150_000_000, true)).toBe("1.5억");
    expect(formatWon(50_000, true)).toBe("5만");
  });

  it("abbreviated 임계값 미만은 일반 표기로 fallback", () => {
    expect(formatWon(5000, true)).toBe("5,000원");
  });
});

describe("formatDate", () => {
  it("null/undefined는 dash", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("ISO datetime의 YYYY-MM-DD만 점으로 변환", () => {
    expect(formatDate("2026-05-13T10:30:00+09:00")).toBe("2026.05.13");
    expect(formatDate("2026-05-13")).toBe("2026.05.13");
  });
});

describe("formatDateTime", () => {
  it("null/undefined/빈문자열은 dash", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });

  it("invalid ISO도 안전하게 dash 반환", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("UTC datetime을 KST로 변환해 표기 (+9시간)", () => {
    // 2026-05-13 01:30 UTC = 2026-05-13 10:30 KST
    const result = formatDateTime("2026-05-13T01:30:00Z");
    expect(result).toContain("2026");
    expect(result).toContain("05");
    expect(result).toContain("13");
    expect(result).toContain("10:30");
  });
});
