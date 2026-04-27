"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "./AuthGuard";
import { clearAuth } from "@/lib/auth";
import type { UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  roles?: UserRole[]; // 미지정 시 모든 사용자 접근 가능
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
  { href: "/schedule", label: "직원 일정" },
  { href: "/utilities", label: "유틸 런처" },
  { href: "/admin/employees", label: "직원 관리", roles: ["admin"] },
  { href: "/admin/users", label: "사용자 관리", roles: ["admin"] },
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
          const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
          return (
            <Link
              key={n.href}
              href={n.href}
              onClick={onCloseMobile}
              className={cn(
                "block rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-100",
              )}
            >
              {n.label}
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
