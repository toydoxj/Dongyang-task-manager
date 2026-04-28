"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { checkAuthStatus } from "@/lib/auth";

import LoginForm from "./LoginForm";

export default function LoginPage() {
  const router = useRouter();
  const [worksEnabled, setWorksEnabled] = useState(false);

  useEffect(() => {
    void checkAuthStatus()
      .then((s) => setWorksEnabled(!!s.works_enabled))
      .catch(() => {});
  }, []);

  return (
    <LoginForm
      isSetup={false}
      worksEnabled={worksEnabled}
      onSuccess={() => router.replace("/me")}
    />
  );
}
