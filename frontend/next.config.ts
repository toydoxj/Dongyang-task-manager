import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // PR-EJ/EK (4-D 1·2단계): admin URL 재구성 — 운영성 페이지를 /operations/ 하위로
  // 이동. 옛 북마크 + 사내 다른 페이지의 미갱신 link 호환을 위해 308(영구) redirect.
  // 주: PR-EJ commit에서 next.config.ts 변경이 누락된 것을 PR-EK 작업 중 발견 →
  // 5건 모두 PR-EK에서 보강.
  async redirects() {
    return [
      {
        source: "/admin/incomes/clients",
        destination: "/operations/incomes/clients",
        permanent: true,
      },
      {
        source: "/admin/incomes",
        destination: "/operations/incomes",
        permanent: true,
      },
      {
        source: "/admin/expenses",
        destination: "/operations/expenses",
        permanent: true,
      },
      {
        source: "/admin/contracts",
        destination: "/operations/contracts",
        permanent: true,
      },
      {
        source: "/admin/employee-work",
        destination: "/operations/employee-work",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
