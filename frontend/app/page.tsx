"use client";

import { useAuth } from "@/components/AuthGuard";

export default function DashboardPage() {
  const { user } = useAuth();
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">대시보드</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {user?.name || user?.username} 님 환영합니다.
        </p>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Placeholder title="진행단계별 칸반" caption="A1 — Phase 3 구현 예정" />
        <Placeholder title="월별 매출/수금 콤보" caption="A4 — Phase 3 구현 예정" />
        <Placeholder title="시작전 TASK 적체" caption="A8 — Phase 3 후반" />
      </section>
    </div>
  );
}

function Placeholder({ title, caption }: { title: string; caption: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mt-1 text-xs text-zinc-500">{caption}</p>
      <div className="mt-4 flex h-32 items-center justify-center rounded-md border border-dashed border-zinc-300 text-xs text-zinc-400 dark:border-zinc-700">
        준비 중
      </div>
    </div>
  );
}
