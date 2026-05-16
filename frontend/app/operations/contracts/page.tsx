"use client";

import UnauthorizedRedirect from "@/components/UnauthorizedRedirect";
import { useRoleGuard } from "@/lib/useRoleGuard";

export default function ContractsAdminPage() {
  // 운영(계약서) — admin + manager. 사이드바 노출과 정합 맞춤.
  const { user, allowed } = useRoleGuard(["admin", "manager"]);

  if (user && !allowed) {
    return (
      <UnauthorizedRedirect
        message="계약서 관리 권한이 없습니다."
        targetPath="/"
      />
    );
  }

  return (
    <main className="p-6">
      <header className="mb-4">
        <h1 className="text-2xl font-semibold">계약서 관리</h1>
        <p className="mt-1 text-sm text-zinc-500">
          프로젝트 계약서를 등록·열람·다운로드합니다.
        </p>
      </header>
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 px-6 py-10 text-center">
        <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
          준비 중인 페이지입니다.
        </p>
        <p className="mt-2 text-xs text-zinc-500">
          계약서 업로드·검색 기능은 후속 단계에서 제공될 예정입니다.
        </p>
      </div>
    </main>
  );
}
