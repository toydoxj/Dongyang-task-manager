"use client";

import { useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import {
  approveUser,
  deleteUser,
  listUsers,
  rejectUser,
} from "@/lib/api";
import type { UserInfo } from "@/lib/types";
import { cn } from "@/lib/utils";

type UserView = "pending" | "active" | "all";

export default function UsersAdminPage() {
  const { user } = useAuth();
  const [view, setView] = useState<UserView>("pending");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const { data, mutate, error, isLoading } = useSWR(
    user?.role === "admin" ? ["users"] : null,
    () => listUsers(),
  );

  if (user && user.role !== "admin") {
    return (
      <main className="p-6">
        <p className="text-sm text-red-500">관리자 권한이 필요합니다.</p>
      </main>
    );
  }

  const filtered = (data ?? []).filter((u) => {
    if (view === "all") return true;
    if (view === "pending") return u.status === "pending";
    if (view === "active") return u.status === "active";
    return true;
  });

  const counts = {
    pending: (data ?? []).filter((u) => u.status === "pending").length,
    active: (data ?? []).filter((u) => u.status === "active").length,
    all: (data ?? []).length,
  };

  async function onApprove(id: number) {
    try {
      await approveUser(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "승인 실패");
    }
  }

  async function onReject(id: number) {
    if (!confirm("가입을 거절하시겠습니까?")) return;
    try {
      await rejectUser(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "거절 실패");
    }
  }

  async function onDelete(id: number) {
    if (!confirm("사용자를 영구 삭제하시겠습니까?")) return;
    try {
      await deleteUser(id);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "삭제 실패");
    }
  }

  return (
    <main className="space-y-4 p-6">
      <header>
        <h1 className="text-lg font-semibold">사용자 관리</h1>
        <p className="mt-0.5 text-xs text-zinc-500">
          가입 신청 승인/거절, 활성 사용자 관리. 이메일이 직원 명부에 있으면
          자동 승인됩니다.
        </p>
      </header>

      <div className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {(
          [
            ["pending", `승인 대기 (${counts.pending})`],
            ["active", `활성 (${counts.active})`],
            ["all", `전체 (${counts.all})`],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setView(k)}
            className={cn(
              "border-b-2 px-3 py-1.5 text-xs",
              view === k
                ? "border-blue-500 text-blue-600 dark:text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {errMsg && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-sm text-red-500">
          {errMsg}
        </p>
      )}
      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/5 p-2 text-sm text-red-500">
          {error instanceof Error ? error.message : "로드 실패"}
        </p>
      )}

      <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs text-zinc-500 dark:bg-zinc-900">
            <tr>
              <th className="px-3 py-2">아이디</th>
              <th className="px-3 py-2">이름</th>
              <th className="px-3 py-2">이메일</th>
              <th className="px-3 py-2">권한</th>
              <th className="px-3 py-2">상태</th>
              <th className="px-3 py-2 text-right">관리</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && !data && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-xs text-zinc-500">
                  불러오는 중…
                </td>
              </tr>
            )}
            {filtered.map((u) => (
              <UserRow
                key={u.id}
                u={u}
                onApprove={() => void onApprove(u.id)}
                onReject={() => void onReject(u.id)}
                onDelete={() => void onDelete(u.id)}
                isMe={u.id === user?.id}
              />
            ))}
            {data && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-xs text-zinc-500">
                  {view === "pending" ? "승인 대기 중인 사용자가 없습니다." : "사용자가 없습니다."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}

const cellCls = "px-3 py-2 align-middle";

function UserRow({
  u,
  onApprove,
  onReject,
  onDelete,
  isMe,
}: {
  u: UserInfo;
  onApprove: () => void;
  onReject: () => void;
  onDelete: () => void;
  isMe: boolean;
}) {
  return (
    <tr className="border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
      <td className={cn(cellCls, "font-mono text-xs")}>{u.username}</td>
      <td className={cellCls}>{u.name || "—"}</td>
      <td className={cn(cellCls, "text-zinc-500")}>{u.email || "—"}</td>
      <td className={cellCls}>
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-[10px]",
            u.role === "admin"
              ? "bg-purple-500/15 text-purple-600 dark:text-purple-400"
              : "bg-zinc-500/15 text-zinc-500",
          )}
        >
          {u.role}
        </span>
      </td>
      <td className={cellCls}>
        <StatusBadge status={u.status} />
      </td>
      <td className={cn(cellCls, "text-right whitespace-nowrap")}>
        {u.status === "pending" && (
          <>
            <button
              type="button"
              onClick={onApprove}
              className="rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700"
            >
              승인
            </button>
            <button
              type="button"
              onClick={onReject}
              className="ml-1 rounded border border-red-300 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
            >
              거절
            </button>
          </>
        )}
        {!isMe && u.status !== "pending" && (
          <button
            type="button"
            onClick={onDelete}
            className="rounded border border-red-300 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
          >
            삭제
          </button>
        )}
        {isMe && (
          <span className="text-[10px] text-zinc-400">(나)</span>
        )}
      </td>
    </tr>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, [string, string]> = {
    active: ["활성", "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"],
    pending: ["대기", "bg-amber-500/15 text-amber-600 dark:text-amber-400"],
    rejected: ["거절", "bg-red-500/15 text-red-500"],
  };
  const [label, cls] = cfg[status] ?? [status, "bg-zinc-500/15 text-zinc-500"];
  return <span className={cn("rounded px-1.5 py-0.5 text-[10px]", cls)}>{label}</span>;
}
