import type { NextConfig } from "next";

// Electron 패키징 시 정적 export — 백엔드(FastAPI)가 frontend/out/ 을 서빙한다.
// dev 모드에서는 평소대로 next dev 사용.
const isElectronBuild = process.env.NEXT_BUILD_TARGET === "electron";

const nextConfig: NextConfig = {
  ...(isElectronBuild && {
    output: "export",
    // 정적 export 시 / → /index.html 매칭 위해
    trailingSlash: true,
    // 정적 export 시 next/image optimization 비활성
    images: { unoptimized: true },
    // packaged 빌드는 .env.local 의 NEXT_PUBLIC_API_BASE 를 무시하고
    // 런타임에 window.location.origin 을 사용해야 backend random port 와 일치.
    env: { NEXT_PUBLIC_API_BASE: "" },
  }),
};

export default nextConfig;
