"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthGuard";
import LoadingState from "@/components/ui/LoadingState";
import {
  downloadWeeklyReportPdf,
  fetchWeeklyReportPdfBlob,
} from "@/lib/api";

/** 주어진 날짜가 속한 주의 월요일 (KST 가정). */
function mondayOf(d: Date): Date {
  const date = new Date(d);
  const day = date.getDay();
  const diff = day === 0 ? -6 : 1 - day; // 일요일이면 6일 전, 그 외엔 (1-day)일 전
  date.setDate(date.getDate() + diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function WeeklyReportPage() {
  const { user } = useAuth();
  const [weekStart, setWeekStart] = useState<string>(
    toIsoDate(mondayOf(new Date())),
  );
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // weekStart 변경 시 PDF blob fetch → ObjectURL 발급. 언마운트/재요청 시 revoke.
  useEffect(() => {
    if (!user || !weekStart) return;
    let revokedUrl: string | null = null;
    let cancelled = false;

    setLoading(true);
    setError(null);
    fetchWeeklyReportPdfBlob(weekStart)
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revokedUrl = url;
        setPdfUrl(url);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "PDF 로드 실패");
        setPdfUrl(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (revokedUrl) URL.revokeObjectURL(revokedUrl);
    };
  }, [user, weekStart]);

  const handleDateChange = (value: string): void => {
    if (!value) return;
    const d = new Date(`${value}T00:00:00`);
    if (Number.isNaN(d.getTime())) return;
    setWeekStart(toIsoDate(mondayOf(d)));
  };

  const handleDownload = async (): Promise<void> => {
    setDownloading(true);
    try {
      await downloadWeeklyReportPdf(weekStart);
    } catch (e) {
      alert(e instanceof Error ? e.message : "PDF 다운로드 실패");
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-2rem)] flex-col gap-3">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">주간 업무일지</h1>
          <p className="mt-1 text-sm text-zinc-500">
            월~금 주차 단위 자동 집계 PDF (KST). 데이터: 노션 미러 + employees + 공지.
          </p>
        </div>
        <div className="flex items-end gap-2">
          <label className="flex flex-col text-xs text-zinc-500">
            주차 시작 (월요일)
            <input
              type="date"
              value={weekStart}
              onChange={(e) => handleDateChange(e.target.value)}
              className="mt-1 rounded border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </label>
          <button
            onClick={handleDownload}
            disabled={downloading || !pdfUrl}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {downloading ? "다운로드 중..." : "PDF 다운로드"}
          </button>
        </div>
      </header>

      {loading && <LoadingState />}
      {error && (
        <div className="rounded-md border border-red-500/40 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      {pdfUrl && !error && (
        <iframe
          src={pdfUrl}
          title={`주간 업무일지 ${weekStart}`}
          className="min-h-[600px] w-full flex-1 rounded border border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900"
        />
      )}
    </div>
  );
}
