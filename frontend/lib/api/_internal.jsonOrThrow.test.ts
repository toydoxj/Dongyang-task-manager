import { describe, expect, it } from "vitest";

import { jsonOrThrow } from "./_internal";

/**
 * PR-FA: jsonOrThrow boundary 검증.
 *
 * lib/api/* 도메인 호출자가 모두 사용 — 응답 status/body schema 변경 시
 * 잘못된 throw / 누락된 에러 자동 검출.
 */
describe("jsonOrThrow (PR-FA)", () => {
  it("200 → JSON body 그대로 반환", async () => {
    const data = { items: [1, 2, 3], count: 3 };
    const res = new Response(JSON.stringify(data), { status: 200 });
    const result = await jsonOrThrow<typeof data>(res);
    expect(result).toEqual(data);
  });

  it("201 (Created) 도 ok=true → JSON 반환", async () => {
    const data = { id: "abc" };
    const res = new Response(JSON.stringify(data), { status: 201 });
    const result = await jsonOrThrow<typeof data>(res);
    expect(result).toEqual(data);
  });

  it("400 + {detail} JSON → detail 메시지로 throw", async () => {
    const res = new Response(JSON.stringify({ detail: "잘못된 입력" }), {
      status: 400,
    });
    await expect(jsonOrThrow(res)).rejects.toThrow("잘못된 입력");
  });

  it("404 + {detail} JSON → detail 메시지로 throw", async () => {
    const res = new Response(JSON.stringify({ detail: "찾을 수 없음" }), {
      status: 404,
    });
    await expect(jsonOrThrow(res)).rejects.toThrow("찾을 수 없음");
  });

  it("500 + detail 없는 JSON → status statusText fallback", async () => {
    const res = new Response(JSON.stringify({}), {
      status: 500,
      statusText: "Internal Server Error",
    });
    await expect(jsonOrThrow(res)).rejects.toThrow(
      /500 Internal Server Error/,
    );
  });

  it("500 + non-JSON body → status statusText fallback (JSON parse 실패 graceful)", async () => {
    const res = new Response("<html>500</html>", {
      status: 500,
      statusText: "Internal Server Error",
    });
    await expect(jsonOrThrow(res)).rejects.toThrow(
      /500 Internal Server Error/,
    );
  });

  it("400 + 빈 body → status statusText fallback", async () => {
    const res = new Response("", { status: 400, statusText: "Bad Request" });
    await expect(jsonOrThrow(res)).rejects.toThrow(/400 Bad Request/);
  });
});
