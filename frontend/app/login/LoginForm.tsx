"use client";

import { worksLoginUrl } from "@/lib/auth";

interface Props {
  // 호환을 위해 유지하되 사용 안 함
  isSetup?: boolean;
  onSuccess?: () => void;
  worksEnabled?: boolean;
}

export default function LoginForm({ worksEnabled }: Props) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            (주)동양구조
          </p>
          <h1 className="mt-2 text-xl font-semibold text-white">업무관리 시스템</h1>
        </div>

        <div className="space-y-4 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-center text-sm font-semibold text-zinc-300">로그인</h2>
          <p className="text-center text-xs text-zinc-500">
            회사 NAVER WORKS 계정으로만 로그인할 수 있습니다.
          </p>

          {worksEnabled ? (
            <a
              href={worksLoginUrl("/")}
              className="block w-full rounded-lg border border-emerald-700/40 bg-emerald-600/10 py-2.5 text-center text-sm font-medium text-emerald-300 transition hover:bg-emerald-600/20"
            >
              NAVER WORKS로 로그인
            </a>
          ) : (
            <p className="rounded-md border border-amber-700/40 bg-amber-500/5 px-3 py-2 text-center text-xs text-amber-300">
              SSO 설정이 활성화되지 않았습니다. 관리자에게 문의해 주세요.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
