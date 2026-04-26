"use client";

import { useState } from "react";
import useSWR from "swr";

import { useAuth } from "@/components/AuthGuard";
import Modal from "@/components/ui/Modal";
import {
  approveUser,
  deleteUser,
  listUsers,
  rejectUser,
  setUserRole,
  updateUserAsAdmin,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ROLE_LABEL, type UserInfo, type UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

const COMPANY_EMAIL_DOMAIN = "@dyce.kr";

type UserView = "pending" | "active" | "all";

export default function UsersAdminPage() {
  const { user } = useAuth();
  const [view, setView] = useState<UserView>("pending");
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [editing, setEditing] = useState<UserInfo | null>(null);
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

  async function onChangeRole(id: number, role: UserRole) {
    try {
      await setUserRole(id, role);
      await mutate();
    } catch (e) {
      setErrMsg(e instanceof Error ? e.message : "권한 변경 실패");
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
              <th className="px-3 py-2">최근 로그인</th>
              <th className="px-3 py-2 text-right">관리</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && !data && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-xs text-zinc-500">
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
                onChangeRole={(r) => void onChangeRole(u.id, r)}
                onEdit={() => setEditing(u)}
                isMe={u.id === user?.id}
              />
            ))}
            {data && filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-xs text-zinc-500">
                  {view === "pending" ? "승인 대기 중인 사용자가 없습니다." : "사용자가 없습니다."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <UserEditModal
          user={editing}
          onClose={() => setEditing(null)}
          onSaved={(u) => {
            setEditing(null);
            void mutate(
              (prev) => prev?.map((x) => (x.id === u.id ? u : x)) ?? prev,
              { revalidate: true },
            );
          }}
          onError={(m) => setErrMsg(m)}
        />
      )}
    </main>
  );
}

function UserEditModal({
  user,
  onClose,
  onSaved,
  onError,
}: {
  user: UserInfo;
  onClose: () => void;
  onSaved: (u: UserInfo) => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [notionId, setNotionId] = useState(user.notion_user_id);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (email && !email.toLowerCase().endsWith(COMPANY_EMAIL_DOMAIN)) {
      onError(`이메일은 회사 계정(${COMPANY_EMAIL_DOMAIN})만 사용 가능합니다`);
      return;
    }
    setSaving(true);
    try {
      const updated = await updateUserAsAdmin(user.id, {
        name,
        email,
        notion_user_id: notionId,
      });
      onSaved(updated);
    } catch (err) {
      onError(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={`사용자 편집 — ${user.username}`} size="md">
      <form onSubmit={onSubmit} className="space-y-3">
        <div>
          <label className="mb-1 block text-xs text-zinc-500">이름</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-zinc-500">
            이메일 ({COMPANY_EMAIL_DOMAIN})
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={`name${COMPANY_EMAIL_DOMAIN}`}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-950"
          />
          <p className="mt-1 text-[10px] text-zinc-500">
            변경 시 직원 명부 매칭이 자동으로 재시도됩니다.
          </p>
        </div>
        <div>
          <label className="mb-1 block text-xs text-zinc-500">
            노션 사용자 ID (선택)
          </label>
          <input
            type="text"
            value={notionId}
            onChange={(e) => setNotionId(e.target.value)}
            placeholder="UUID 형식"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-zinc-700 dark:bg-zinc-950"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const cellCls = "px-3 py-2 align-middle";

function UserRow({
  u,
  onApprove,
  onReject,
  onDelete,
  onChangeRole,
  onEdit,
  isMe,
}: {
  u: UserInfo;
  onApprove: () => void;
  onReject: () => void;
  onDelete: () => void;
  onChangeRole: (role: UserRole) => void;
  onEdit: () => void;
  isMe: boolean;
}) {
  const roleColors: Record<UserRole, string> = {
    admin: "bg-purple-500/15 text-purple-600 dark:text-purple-400",
    team_lead: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
    member: "bg-zinc-500/15 text-zinc-500",
  };
  return (
    <tr className="border-t border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900">
      <td className={cn(cellCls, "font-mono text-xs")}>{u.username}</td>
      <td className={cellCls}>{u.name || "—"}</td>
      <td className={cn(cellCls, "text-zinc-500")}>{u.email || "—"}</td>
      <td className={cellCls}>
        {u.status === "active" ? (
          <select
            value={u.role}
            onChange={(e) => onChangeRole(e.target.value as UserRole)}
            className={cn(
              "rounded border-0 px-1.5 py-0.5 text-[11px] font-medium outline-none",
              roleColors[u.role],
            )}
          >
            <option value="admin">{ROLE_LABEL.admin}</option>
            <option value="team_lead">{ROLE_LABEL.team_lead}</option>
            <option value="member">{ROLE_LABEL.member}</option>
          </select>
        ) : (
          <span className={cn("rounded px-1.5 py-0.5 text-[10px]", roleColors[u.role])}>
            {ROLE_LABEL[u.role]}
          </span>
        )}
      </td>
      <td className={cellCls}>
        <StatusBadge status={u.status} />
      </td>
      <td className={cn(cellCls, "text-xs text-zinc-500 whitespace-nowrap")}>
        {formatDateTime(u.last_login_at)}
      </td>
      <td className={cn(cellCls, "text-right whitespace-nowrap")}>
        <button
          type="button"
          onClick={onEdit}
          className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-600 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
        >
          편집
        </button>
        {u.status === "pending" && (
          <>
            <button
              type="button"
              onClick={onApprove}
              className="ml-1 rounded bg-emerald-600 px-2 py-0.5 text-[11px] text-white hover:bg-emerald-700"
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
            className="ml-1 rounded border border-red-300 px-2 py-0.5 text-[11px] text-red-500 hover:bg-red-50 dark:border-red-900 dark:hover:bg-red-950"
          >
            삭제
          </button>
        )}
        {isMe && (
          <span className="ml-1 text-[10px] text-zinc-400">(나)</span>
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
