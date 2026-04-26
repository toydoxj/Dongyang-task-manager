"use client";

import { useRouter } from "next/navigation";

import LoginForm from "./LoginForm";

export default function LoginPage() {
  const router = useRouter();
  return <LoginForm isSetup={false} onSuccess={() => router.replace("/me")} />;
}
