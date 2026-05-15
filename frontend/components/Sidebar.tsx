"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import useSWR from "swr";

import { useAuth } from "./AuthGuard";
import { getSealPendingCount } from "@/lib/api";
import { backendLogout, clearAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  roles?: UserRole[]; // 미지정 시 모든 사용자 접근 가능
  /** 이 role에게는 명시적으로 hide (roles와 별도). manager용 — 9개 메뉴만 노출. */
  hiddenForRoles?: UserRole[];
  external?: boolean; // true면 새 탭으로 열기 (next/link 대신 <a target="_blank">)
}

interface NavGroup {
  /** 그룹 헤더 라벨. null이면 헤더 미표시(첫 그룹). */
  label: string | null;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  // 공통 — 일반 사용자 작업 영역. manager는 일부만 노출.
  {
    label: null,
    items: [
      { href: "/", label: "대시보드", roles: ["admin", "team_lead", "manager"] },
      { href: "/me", label: "내 업무", hiddenForRoles: ["manager"] },
      {
        href: "/admin/employee-work",
        label: "직원 업무",
        roles: ["admin", "team_lead"],
      },
      // 직원 일정은 task.dyce.kr 내부 FullCalendar에서 보기. NAVER WORKS Calendar에는 backend가 단방향 동기화.
      { href: "/schedule", label: "직원 일정" },
      { href: "/seal-requests", label: "날인요청", hiddenForRoles: ["manager"] },
      { href: "/suggestions", label: "건의사항" },
      // 주간업무일지는 /me 또는 대시보드 우상단 '주간업무일지 보기' 버튼에서 진입.
      { href: "/utilities", label: "유틸 런처", hiddenForRoles: ["manager"] },
      { href: "/help", label: "사용 매뉴얼" },
    ],
  },
  // 운영 — admin + manager. 프로젝트·영업·발주처·돈·계약 흐름.
  {
    label: "운영 관리",
    items: [
      { href: "/projects", label: "프로젝트", roles: ["admin", "team_lead", "manager"] },
      { href: "/sales", label: "영업 관리", roles: ["admin", "team_lead", "manager"] },
      {
        href: "/admin/incomes/clients",
        label: "발주처 관리",
        roles: ["admin", "manager"],
      },
      { href: "/admin/incomes", label: "수금 관리", roles: ["admin", "manager"] },
      // 지출 관리 / 계약서 관리는 페이지 미구현 — placeholder route. 추후 page 추가 시 link 활성화.
      { href: "/admin/expenses", label: "지출 관리", roles: ["admin", "manager"] },
      { href: "/admin/contracts", label: "계약서 관리", roles: ["admin", "manager"] },
    ],
  },
  // 시스템 — admin only. 공지·직원·사용자·Drive 등 인프라 설정.
  {
    label: "시스템 관리",
    items: [
      { href: "/admin/notices", label: "공지/교육 관리", roles: ["admin"] },
      { href: "/admin/employees", label: "직원 관리", roles: ["admin"] },
      { href: "/admin/users", label: "사용자 관리", roles: ["admin"] },
      { href: "/admin/sync", label: "Sync 관리", roles: ["admin"] },
      { href: "/admin/drive", label: "Drive 연결", roles: ["admin"] },
    ],
  },
];

interface Props {
  /** 모바일에서 drawer가 열려있는지. lg 이상에선 무시. */
  mobileOpen: boolean;
  /** 모바일 link 클릭 시 자동 close. */
  onCloseMobile: () => void;
}

export default function Sidebar({ mobileOpen, onCloseMobile }: Props) {
  const pathname = usePathname();
  const { user } = useAuth();

  // 날인요청 처리 대기 카운트 (admin/team_lead만, 60초 간격 polling)
  const showSealBadge =
    user?.role === "admin" || user?.role === "team_lead";
  const { data: sealPending } = useSWR(
    showSealBadge ? ["seal-pending"] : null,
    () => getSealPendingCount(),
    { refreshInterval: 60_000 },
  );
  const sealCount = sealPending?.count ?? 0;

  const handleLogout = async (): Promise<void> => {
    // PR-BH: backend cookie 제거 + DB session 무효화. 실패해도 로컬 clearAuth 진행.
    await backendLogout();
    clearAuth();
    window.location.href = "/login";
  };

  // label 있는 그룹의 펼침 상태 (default 펼침). 사용자 클릭으로 toggle.
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const toggleGroup = (label: string): void =>
    setCollapsedGroups((prev) => ({ ...prev, [label]: !prev[label] }));

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-zinc-800 bg-zinc-950 text-zinc-200 transition-transform",
        // 모바일: 기본 숨김 → mobileOpen 시 슬라이드
        mobileOpen ? "translate-x-0" : "-translate-x-full",
        // 데스크톱(lg 이상): 항상 표시
        "lg:translate-x-0",
      )}
    >
      <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
        <Link
          href="/"
          onClick={onCloseMobile}
          className="flex items-center gap-2.5"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.svg" alt="동양구조" className="h-8 w-8 shrink-0" />
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              (주)동양구조
            </p>
            <h1 className="text-sm font-semibold leading-tight">업무관리</h1>
          </div>
        </Link>
        {/* 모바일 닫기 버튼 */}
        <button
          type="button"
          onClick={onCloseMobile}
          aria-label="메뉴 닫기"
          className="rounded p-1 text-zinc-400 hover:bg-zinc-800 lg:hidden"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="h-5 w-5"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <nav className="flex-1 space-y-3 overflow-y-auto p-3">
        {NAV_GROUPS.map((group, gi) => {
          const visibleItems = group.items.filter((n) => {
            if (!user?.role) return false;
            if (n.hiddenForRoles?.includes(user.role)) return false;
            if (n.roles && !n.roles.includes(user.role)) return false;
            return true;
          });
          if (visibleItems.length === 0) return null;
          const collapsed = group.label
            ? !!collapsedGroups[group.label]
            : false;
          return (
            <div key={`group-${gi}`} className="space-y-1">
              {group.label && (
                <button
                  type="button"
                  onClick={() => toggleGroup(group.label as string)}
                  aria-expanded={!collapsed}
                  className="flex w-full items-center justify-between px-3 pt-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 hover:text-zinc-300"
                >
                  <span>{group.label}</span>
                  <span className="text-zinc-500">{collapsed ? "▶" : "▼"}</span>
                </button>
              )}
              {!collapsed && visibleItems.map((n) => {
                const active =
                  !n.external &&
                  (pathname === n.href || pathname.startsWith(`${n.href}/`));
                const showBadge =
                  n.href === "/seal-requests" && showSealBadge && sealCount > 0;
                const itemClass = cn(
                  "flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-zinc-800 text-white"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
                );
                if (n.external) {
                  return (
                    <a
                      key={n.href}
                      href={n.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={onCloseMobile}
                      className={itemClass}
                    >
                      <span>{n.label}</span>
                      <span className="text-xs text-zinc-500">↗</span>
                    </a>
                  );
                }
                return (
                  <Link
                    key={n.href}
                    href={n.href}
                    onClick={onCloseMobile}
                    className={itemClass}
                  >
                    <span>{n.label}</span>
                    {showBadge && (
                      <span className="rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-medium text-white">
                        {sealCount}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          );
        })}
      </nav>

      {user && (
        <div className="border-t border-zinc-800 p-4">
          <div className="mb-2">
            <p className="text-sm font-medium text-zinc-100">
              {user.name || user.username}
            </p>
            <p className="text-xs text-zinc-500">{user.role}</p>
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="w-full rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          >
            로그아웃
          </button>
        </div>
      )}
    </aside>
  );
}
