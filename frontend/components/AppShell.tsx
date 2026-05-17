"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import AuthGuard from "./AuthGuard";
import ProjectDetailModal from "./common/ProjectDetailModal";
import SaleDetailModal from "./common/SaleDetailModal";
import Sidebar from "./Sidebar";

/**
 * useSearchParams를 사용하는 inner component. Next.js 16은 prerender 시
 * useSearchParams가 Suspense 밖에 있으면 CSR bailout → /_not-found 등 static
 * page export 실패. 별도 컴포넌트로 분리 + Suspense로 wrap.
 */
function ShellBody({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);
  // PR-FQ: ?popup=1 query가 있으면 사이드바·모바일 헤더 없는 chromeless layout.
  // openInPopup에서 자동 부착 — 사용자가 직접 URL 입력해도 동일 동작.
  const sp = useSearchParams();
  const isPopup = sp?.get("popup") === "1";

  if (isPopup) {
    return (
      <>
        <main className="min-h-screen bg-zinc-50 p-4 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100 sm:p-6">
          {children}
        </main>
        <ProjectDetailModal />
        <SaleDetailModal />
      </>
    );
  }

  return (
    <>
      <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <Sidebar mobileOpen={navOpen} onCloseMobile={() => setNavOpen(false)} />

        {/* 모바일 backdrop */}
        {navOpen && (
          <button
            type="button"
            aria-label="메뉴 닫기"
            onClick={() => setNavOpen(false)}
            className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          />
        )}

        <div className="flex min-h-screen w-full min-w-0 flex-col lg:ml-64">
          {/* 모바일 상단 바 (lg 이상에선 숨김) */}
          <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-950 lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="메뉴 열기"
              className="rounded-md p-1.5 text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="h-5 w-5"
              >
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/logo.svg" alt="동양구조" className="h-6 w-6" />
            <span className="text-sm font-semibold">업무관리</span>
          </header>

          <main className="mx-auto w-full min-w-0 max-w-[1600px] flex-1 p-4 text-zinc-900 dark:text-zinc-100 sm:p-6">
            {children}
          </main>
        </div>
      </div>
      <ProjectDetailModal />
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  // ShellBody가 useSearchParams를 사용하므로 Suspense로 감싼다.
  // fallback은 일반 사이드바 layout — 일순간 차이가 거의 보이지 않음 (대다수 진입은 ?popup이 없음).
  return (
    <AuthGuard>
      <Suspense fallback={<div className="min-h-screen bg-zinc-50 dark:bg-zinc-950" />}>
        <ShellBody>{children}</ShellBody>
      </Suspense>
    </AuthGuard>
  );
}
