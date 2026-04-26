"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "./AuthGuard";
import { clearAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { href: "/", label: "대시보드" },
  { href: "/projects", label: "프로젝트" },
  { href: "/me", label: "내 업무" },
  { href: "/utilities", label: "유틸 런처" },
  { href: "/admin/users", label: "사용자 관리", adminOnly: true },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const handleLogout = (): void => {
    clearAuth();
    window.location.href = "/login";
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-10 flex w-64 flex-col border-r border-zinc-800 bg-zinc-950 text-zinc-200">
      <div className="border-b border-zinc-800 px-5 py-4">
        <Link href="/" className="flex items-center gap-2.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo.svg"
            alt="동양구조"
            className="h-8 w-8 shrink-0"
          />
          <div className="min-w-0">
            <p className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
              (주)동양구조
            </p>
            <h1 className="text-sm font-semibold leading-tight">업무관리</h1>
          </div>
        </Link>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.filter((n) => !n.adminOnly || user?.role === "admin").map((n) => {
          const active = pathname === n.href || pathname.startsWith(`${n.href}/`);
          return (
            <Link
              key={n.href}
              href={n.href}
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
            <p className="text-sm font-medium text-zinc-100">{user.name || user.username}</p>
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
