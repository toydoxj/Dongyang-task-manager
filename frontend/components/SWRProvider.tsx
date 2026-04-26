"use client";

import { SWRConfig } from "swr";

export default function SWRProvider({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        // 같은 키 1분 내 중복 호출 합치기 (페이지 이동 시 중요)
        dedupingInterval: 60_000,
        // 백그라운드 리페치 비활성 (노션 rate limit 보호)
        revalidateOnFocus: false,
        // 네트워크 복귀 시 재검증
        revalidateOnReconnect: true,
        // 에러 시 자동 재시도 (3회까지)
        errorRetryCount: 3,
        errorRetryInterval: 2000,
      }}
    >
      {children}
    </SWRConfig>
  );
}
