"use client";

import { useEffect, useState } from "react";

import { authFetch } from "@/lib/auth";
import { API_BASE } from "@/lib/types";

interface DriveStatus {
  connected: boolean;
  scope?: string;
  granted_by_email?: string;
  expires_at?: string | null;
  seconds_left?: number | null;
  has_refresh_token?: boolean;
  updated_at?: string | null;
}

function fmtRemaining(seconds?: number | null): string {
  if (seconds == null) return "—";
  if (seconds <= 0) return "만료";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}시간 ${m}분`;
}

function fmtDateTime(iso?: string | null): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return iso;
  }
}

export default function DriveAdminPage() {
  const [status, setStatus] = useState<DriveStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.get("drive_connected") === "1") {
        setInfo("WORKS Drive 연결이 완료되었습니다.");
        window.history.replaceState(null, "", window.location.pathname);
      } else if (params.get("drive_error")) {
        setError(`연결 실패: ${params.get("drive_error")}`);
        window.history.replaceState(null, "", window.location.pathname);
      }
    }
    void load();
  }, []);

  async function load(): Promise<void> {
    setLoading(true);
    try {
      const res = await authFetch("/api/admin/drive/status");
      if (!res.ok) throw new Error(`status ${res.status}`);
      const body = (await res.json()) as DriveStatus;
      setStatus(body);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">WORKS Drive 연결</h1>
        <p className="mt-1 text-sm text-zinc-500">
          NAVER WORKS Drive API는 user 토큰만 받기 때문에 admin 한 명이 한 번
          동의해 둔 토큰으로 모든 자동 폴더 생성을 처리합니다. 만료되면 refresh
          토큰으로 자동 갱신됩니다.
        </p>
      </header>

      {info && (
        <div className="rounded-md border border-emerald-700/40 bg-emerald-500/5 p-3 text-sm text-emerald-300">
          {info}
        </div>
      )}
      {error && (
        <div className="rounded-md border border-red-700/40 bg-red-500/5 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold">현재 상태</h2>

        {loading ? (
          <p className="mt-3 text-sm text-zinc-500">조회 중...</p>
        ) : status?.connected ? (
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <Field label="연결" value="✓ 활성" valueClass="text-emerald-400" />
            <Field
              label="scope"
              value={status.scope || "—"}
              valueClass="font-mono"
            />
            <Field label="동의한 admin" value={status.granted_by_email || "—"} />
            <Field
              label="access_token 남은 시간"
              value={fmtRemaining(status.seconds_left)}
            />
            <Field label="refresh 가능" value={status.has_refresh_token ? "✓" : "✗"} />
            <Field label="마지막 갱신" value={fmtDateTime(status.updated_at)} />
          </dl>
        ) : (
          <p className="mt-3 text-sm text-zinc-500">
            아직 연결되지 않았습니다. 아래 버튼을 눌러 NAVER WORKS에 동의해
            주세요.
          </p>
        )}

        <div className="mt-5">
          <a
            href={`${API_BASE}/api/auth/works/login?drive=1&next=${encodeURIComponent("/admin/drive")}`}
            className="inline-block rounded-lg border border-emerald-700/40 bg-emerald-600/10 px-4 py-2 text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/20"
          >
            {status?.connected
              ? "🔄 다시 연결 (재동의)"
              : "🔗 WORKS Drive 연결"}
          </a>
        </div>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
        <h2 className="text-sm font-semibold">동작 방식</h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-zinc-600 dark:text-zinc-400">
          <li>admin이 한 번 동의 → access_token + refresh_token이 서버 DB에 저장</li>
          <li>
            프로젝트 생성 시 자동으로 [업무관리]/[CODE]프로젝트명/{"{1.~7.}"} 폴더
            생성
          </li>
          <li>access_token은 24시간 만료 → refresh_token으로 자동 갱신</li>
          <li>refresh도 거부되면 admin이 다시 연결 필요</li>
        </ul>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <>
      <dt className="text-zinc-500">{label}</dt>
      <dd className={`text-zinc-800 dark:text-zinc-200 ${valueClass ?? ""}`}>
        {value}
      </dd>
    </>
  );
}
