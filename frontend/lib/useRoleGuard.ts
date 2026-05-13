"use client";

import { useAuth } from "@/components/AuthGuard";
import type { UserInfo, UserRole } from "@/lib/types";

/**
 * Phase 4-E (PR-BS): page 진입 권한 체크 hook.
 *
 * 다양한 page에서 반복되는 `const allowed = user?.role === "..." || ...` 패턴을
 * 하나로 통합. 호출 후:
 *   - user가 null/undefined → loading 단계 (호출자에서 `if (!user) return null` 처리)
 *   - user는 있는데 allowed=false → 호출자가 `<UnauthorizedRedirect />` 렌더
 *   - allowed=true → 정상 진행
 *
 * 사용 예:
 *   const { user, allowed } = useRoleGuard(["admin", "team_lead", "manager"]);
 *   if (user && !allowed) return <UnauthorizedRedirect message="..." />;
 */
export function useRoleGuard(allowedRoles: readonly UserRole[]): {
  user: UserInfo | null;
  allowed: boolean;
} {
  const { user } = useAuth();
  const allowed =
    !!user && allowedRoles.includes(user.role as UserRole);
  return { user, allowed };
}
