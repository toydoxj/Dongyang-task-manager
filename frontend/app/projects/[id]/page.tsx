"use client";

import { use } from "react";

import ProjectClient from "@/app/project/ProjectClient";

/**
 * PROJ-005 — 프로젝트 상세 dynamic route.
 *
 * 신규 표준: `/projects/{id}` (REST 스타일).
 * 기존 `/project?id=...`는 `app/project/page.tsx`에서 자동 redirect.
 *
 * Next.js 16부터 page params는 Promise로 전달되어 `use()`로 unwrap.
 */
interface Props {
  params: Promise<{ id: string }>;
}

export default function ProjectDetailPage({ params }: Props) {
  const { id } = use(params);
  return <ProjectClient id={id} />;
}
