/// <reference types="vitest" />
import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * PR-BL-1 (Phase 4-I): Vitest 단위 테스트 설정.
 *
 * 1차 도입 — pure helper(lib/*) 우선. UI/Server Component는 Playwright(별도 cycle).
 * tsconfig의 @/* path alias를 vitest resolve.alias에 별도 명시(Next.js 16과 분리 동작).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", ".next", "dist"],
  },
});
