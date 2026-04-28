"use client";

import { Suspense, useEffect, useState } from "react";

import { checkAuthStatus } from "@/lib/auth";

import LoginForm from "./LoginForm";

export default function LoginPage() {
  const [worksEnabled, setWorksEnabled] = useState(false);

  useEffect(() => {
    void checkAuthStatus()
      .then((s) => setWorksEnabled(!!s.works_enabled))
      .catch(() => {});
  }, []);

  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-zinc-950 text-sm text-zinc-400">
          로딩 중...
        </div>
      }
    >
      <LoginForm isSetup={false} worksEnabled={worksEnabled} />
    </Suspense>
  );
}
