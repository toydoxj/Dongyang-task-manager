"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";

import { useAuth } from "./AuthGuard";
import { getSealPendingCount } from "@/lib/api";
import { clearAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  roles?: UserRole[]; // 미지정 시 모든 사용자 접근 가능
  external?: boolean; // true면 새 탭으로 열기 (next/link 대신 <a target="_blank">)
}

const NAV: NavItem[] = [
  { href: "/", label: "대시보드", roles: ["admin", "team_lead"] },
  { href: "/projects", label: "프로젝트" },
  { href: "/me", label: "내 업무" },
  {
    href: "/admin/employee-work",
    label: "직원 업무",
    roles: ["admin", "team_lead"],
  },
  // 직원 일정은 task.dyce.kr 내부 FullCalendar에서 보기. 등록은 grid에서.
  // NAVER WORKS Calendar 공유 캘린더에는 backend가 단방향 자동 동기화.
  { href: "/schedule", label: "직원 일정" },
  { href: "/suggestions", label: "건의사항" },
  { href: "/seal-requests", label: "날인요청" },
  { href: "/utilities", label: "유틸 런처" },
  { href: "/admin/employees", label: "직원 관리", roles: ["admin"] },
  { href: "/admin/users", label: "사용자 관리", roles: ["admin"] },
  { href: "/admin/drive", label: "Drive 연결", roles: ["admin"] },
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

  const handleLogout = (): void => {
    clearAuth();
    window.location.href = "/login";
  };

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

      <nav className="flex-1 space-y-1 overflow-y-auto p-3">
        {NAV.filter(
          (n) => !n.roles || (user?.role && n.roles.includes(user.role)),
        ).map((n) => {
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
