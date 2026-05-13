import { describe, expect, it } from "vitest";

import { qs } from "./_internal";

/**
 * qs(): 도메인 API 호출에서 query string 빌드 — undefined/null/빈 문자열은 자동 skip.
 * 빈 결과는 ""(prefix '?' 없이) 반환해야 호출처 URL 조립이 깨끗.
 */
describe("qs", () => {
  it("빈 객체는 빈 문자열", () => {
    expect(qs({})).toBe("");
  });

  it("undefined / null / 빈 문자열은 skip", () => {
    expect(qs({ a: undefined, b: null, c: "" })).toBe("");
    expect(qs({ a: "x", b: null, c: undefined, d: "" })).toBe("?a=x");
  });

  it("0 / false 같은 falsy primitive는 포함", () => {
    expect(qs({ count: 0 })).toBe("?count=0");
    expect(qs({ flag: false })).toBe("?flag=false");
  });

  it("URLSearchParams가 한글/특수문자 인코딩", () => {
    const result = qs({ name: "홍길동", q: "a&b" });
    expect(result).toContain("name=%ED%99%8D%EA%B8%B8%EB%8F%99");
    expect(result).toContain("q=a%26b");
  });

  it("number / boolean → string 변환", () => {
    expect(qs({ id: 42 })).toBe("?id=42");
    expect(qs({ open: true })).toBe("?open=true");
  });
});
