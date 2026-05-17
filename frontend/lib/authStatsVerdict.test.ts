import { describe, expect, it } from "vitest";

import {
  GO_THRESHOLD,
  WATCH_THRESHOLD,
  verdictForRatio,
} from "./authStatsVerdict";

/**
 * PR-EZ: verdict 함수 boundary 검증.
 *
 * 임계값 변경 시(GO 0.99 / WATCH 0.95) 잘못된 분기 자동 검출.
 * USER_MANUAL 9.5 + e2e PR-EY와 일관성 보장.
 */
describe("verdictForRatio (PR-EZ)", () => {
  describe("total === 0 → idle", () => {
    it("total 0이면 ratio와 무관하게 idle", () => {
      expect(verdictForRatio(0, 0).tone).toBe("idle");
      expect(verdictForRatio(1, 0).tone).toBe("idle");
      expect(verdictForRatio(0.5, 0).tone).toBe("idle");
      expect(verdictForRatio(0, 0).label).toBe("데이터 없음");
    });
  });

  describe("ratio ≥ 0.99 → go", () => {
    it("1.0 → go", () => {
      expect(verdictForRatio(1.0, 100).tone).toBe("go");
    });
    it("0.99 boundary → go (>=)", () => {
      expect(verdictForRatio(GO_THRESHOLD, 100).tone).toBe("go");
    });
    it("0.995 → go", () => {
      expect(verdictForRatio(0.995, 1000).tone).toBe("go");
    });
    it("go label 포함 \"GO\"", () => {
      expect(verdictForRatio(1.0, 100).label).toMatch(/GO/);
    });
  });

  describe("0.95 ≤ ratio < 0.99 → watch", () => {
    it("0.95 boundary → watch (>=)", () => {
      expect(verdictForRatio(WATCH_THRESHOLD, 100).tone).toBe("watch");
    });
    it("0.96 → watch", () => {
      expect(verdictForRatio(0.96, 100).tone).toBe("watch");
    });
    it("0.9899 → watch (just below GO)", () => {
      expect(verdictForRatio(0.9899, 1000).tone).toBe("watch");
    });
    it("watch label 포함 \"관찰\"", () => {
      expect(verdictForRatio(0.97, 100).label).toMatch(/관찰/);
    });
  });

  describe("ratio < 0.95 → no-go", () => {
    it("0.9499 → no-go (just below WATCH)", () => {
      expect(verdictForRatio(0.9499, 1000).tone).toBe("no-go");
    });
    it("0.5 → no-go", () => {
      expect(verdictForRatio(0.5, 100).tone).toBe("no-go");
    });
    it("0 with total>0 → no-go (header fallback 100%)", () => {
      expect(verdictForRatio(0, 100).tone).toBe("no-go");
    });
    it("no-go label 포함 \"NO-GO\" + header fallback 경고", () => {
      const v = verdictForRatio(0.5, 100);
      expect(v.label).toMatch(/NO-GO/);
      expect(v.detail).toMatch(/header fallback 의존 잔존|PR-EM\/EN 재시도/);
    });
  });

  describe("detail에 비율 % 표기", () => {
    it("0.995 → 99.50% 표기", () => {
      expect(verdictForRatio(0.995, 1000).detail).toMatch(/99\.50%/);
    });
    it("0.5 → 50.00% 표기", () => {
      expect(verdictForRatio(0.5, 100).detail).toMatch(/50\.00%/);
    });
  });
});
