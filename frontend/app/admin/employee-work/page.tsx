"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import { listEmployees } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function EmployeeWorkSelectorPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [q, setQ] = useState("");

  const allowed = user?.role === "admin" || user?.role === "team_lead";
  useEffect(() => {
    if (user && !allowed) router.replace("/me");
  }, [user, allowed, router]);

  const { data, error, isLoading } = useSWR(
    allowed ? ["employees", "active"] : null,
    () => listEmployees(undefined, "active"),
  );
  // 팀장은 본인 employee의 team과 같은 직원만 필터 (admin은 전체)
  const myTeam = useMemo(() => {
    if (user?.role !== "team_lead") return null;
    const items = data?.items ?? [];
    const me = items.find((e) => e.linked_user_id === user.id);
    return me?.team || "";
  }, [data, user]);

  const employees = useMemo(() => {
    let items = data?.items ?? [];
    if (myTeam !== null) {
      items = items.filter((e) => e.team === myTeam);
    }
    if (!q) return items;
    const lower = q.toLowerCase();
    return items.filter(
      (e) =>
        e.name.toLowerCase().includes(lower) ||
        (e.team ?? "").toLowerCase().includes(lower) ||
        (e.position ?? "").toLowerCase().includes(lower),
    );
  }, [data, q, myTeam]);

  // 팀 표시 순서 (본부 → 관리 → 진단 → 구조1~4 → 그 외)
  const TEAM_ORDER = [
    "본부",
    "관리팀",
    "진단팀",
    "구조1팀",
    "구조2팀",
    "구조3팀",
    "구조4팀",
  ];
  // 직급 정렬 순서 (높은 순)
  const POSITION_ORDER = [
    "사장",
    "부사장",
    "전무",
    "상무",
    "이사",
    "실장",
    "차장",
    "과장",
    "대리",
    "기사",
    "사원",
  ];
  const teamOrder = (t: string): number => {
    const idx = TEAM_ORDER.indexOf(t);
    return idx === -1 ? TEAM_ORDER.length : idx;
  };
  const positionOrder = (p: string): number => {
    const idx = POSITION_ORDER.indexOf(p);
    return idx === -1 ? POSITION_ORDER.length : idx;
  };

  // 팀별 그룹핑 + 직급순 정렬
  const grouped = useMemo(() => {
    const map = new Map<string, typeof employees>();
    for (const e of employees) {
      const team = e.team || "기타";
      if (!map.has(team)) map.set(team, []);
      map.get(team)!.push(e);
    }
    // 각 팀 내부 — 직급 순 → 이름 순
    for (const arr of map.values()) {
      arr.sort((a, b) => {
        const dp = positionOrder(a.position) - positionOrder(b.position);
        if (dp !== 0) return dp;
        return a.name.localeCompare(b.name, "ko");
      });
    }
    // 팀 정렬
    return Array.from(map.entries()).sort(
      ([a], [b]) => teamOrder(a) - teamOrder(b),
    );
  }, [employees]);

  if (!user || !allowed) return null;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">직원 업무</h1>
        <p className="mt-1 text-sm text-zinc-500">
          직원을 선택하면 해당 직원이 보는 「내 업무」 화면을 동일하게 표시합니다.
          {user.role === "team_lead" && myTeam
            ? ` (팀장 — ${myTeam} 소속만 표시)`
            : user.role === "admin"
              ? " (관리자 — 전체 직원)"
              : ""}
        </p>
      </header>

      {user.role === "team_lead" && myTeam === "" && (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-500">
          본인의 팀(소속) 정보가 직원 명부에 없습니다. 관리자에게 팀 정보를
          등록해 달라고 요청해 주세요.
        </p>
      )}

      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="이름, 팀, 직급으로 검색..."
        className="w-full max-w-md rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm outline-none dark:border-zinc-700 dark:bg-zinc-950"
      />

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-sm text-red-400">
          {error instanceof Error ? error.message : "직원 명부 로드 실패"}
        </p>
      )}

      {isLoading && !data ? (
        <LoadingState message="직원 명부 불러오는 중" height="h-32" />
      ) : (
        <div className="space-y-5">
          {grouped.map(([team, members]) => (
            <section key={team}>
              <h2 className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-zinc-700 dark:text-zinc-300">
                {team}
                <span className="text-[10px] font-normal text-zinc-500">
                  {members.length}명
                </span>
              </h2>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {members.map((e) => (
                  <li key={e.id}>
                    <Link
                      href={`/me?as=${encodeURIComponent(e.name)}`}
                      className={cn(
                        "block rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-sm transition-colors hover:bg-zinc-50",
                        "dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800",
                      )}
                    >
                      <p className="font-medium">{e.name}</p>
                      <p className="mt-0.5 text-[11px] text-zinc-500">
                        {[e.team, e.position].filter(Boolean).join(" · ") || "—"}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          {grouped.length === 0 && data && (
            <p className="text-center text-xs text-zinc-500">
              {q ? "검색 결과가 없습니다" : "활성 직원이 없습니다"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
