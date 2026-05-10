"use client";

interface NavGroup {
  label: string;
  anchor: string;
  hint: string;
}

const GROUPS: NavGroup[] = [
  { label: "기본 정보", anchor: "headcount", hint: "인원현황" },
  { label: "수동 보완", anchor: "manual-section", hint: "공지 / 교육 / 건의" },
  { label: "자동 집계", anchor: "completed", hint: "완료 / 날인 / 영업 / 신규 / 개인일정 / 팀별업무" },
  { label: "예외·누락", anchor: "waiting", hint: "대기 · 보류 (장기 정체)" },
  { label: "미리보기·발행", anchor: "publish-controls", hint: "PDF 확인 · 발행 버튼 (페이지 상단)" },
];

/** WEEK-002 섹션 점프 nav — 상단 sticky. anchor scroll. */
export default function SectionNav() {
  return (
    <nav
      aria-label="섹션 점프"
      className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-white/95 px-3 py-2 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/95"
    >
      <span className="text-[11px] font-medium text-zinc-500">바로가기</span>
      {GROUPS.map((g) => (
        <a
          key={g.anchor}
          href={`#${g.anchor}`}
          title={g.hint}
          className="rounded-md border border-zinc-300 bg-zinc-50 px-2 py-0.5 text-[11px] text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 dark:hover:bg-zinc-700"
        >
          {g.label}
        </a>
      ))}
    </nav>
  );
}
