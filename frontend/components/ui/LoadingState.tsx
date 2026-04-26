"use client";

import { useEffect, useState } from "react";

interface Props {
  message?: string;
  hint?: string;
  height?: string;
}

export default function LoadingState({
  message = "데이터 불러오는 중…",
  hint = "노션에서 첫 호출은 5~15초 걸릴 수 있습니다 (이후 30초 캐시).",
  height = "h-64",
}: Props) {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setSeconds((s) => s + 1);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      className={`${height} flex flex-col items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900`}
    >
      <div className="flex items-center gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-200">
        <Spinner />
        <span>{message}</span>
      </div>
      <p className="text-[11px] text-zinc-500">
        {seconds}초 경과 · {hint}
      </p>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin text-zinc-500" viewBox="0 0 24 24">
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.2"
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
