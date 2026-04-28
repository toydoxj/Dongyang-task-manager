// SSO callback은 매번 fresh 응답이 필요 (fragment 파싱·토큰 saveAuth 흐름).
// Vercel edge cache의 stale HIT을 차단.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function WorksCallbackLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
