"use client";

import { useState } from "react";

import AuthGuard from "./AuthGuard";
import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = useState(false);

  return (
    <AuthGuard>
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

        <div className="flex min-h-screen w-full flex-col lg:ml-64">
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

          <main className="flex-1 p-4 text-zinc-900 dark:text-zinc-100 sm:p-6">
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
