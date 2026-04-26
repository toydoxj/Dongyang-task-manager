"use client";

import AuthGuard from "./AuthGuard";
import Sidebar from "./Sidebar";

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen bg-zinc-50 dark:bg-zinc-950">
        <Sidebar />
        <main className="ml-64 flex-1 p-6 text-zinc-900 dark:text-zinc-100">
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
