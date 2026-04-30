"use client";

/**
 * 직원 일정 페이지 — NAVER WORKS Calendar로 마이그레이션됨.
 *
 * 직원 외근/출장/휴가 일정은 task.dyce.kr에서 등록 → NAVER WORKS Calendar
 * 회사 공유 캘린더에 자동 동기화되는 단방향 흐름.
 * 보기·알림은 NAVER WORKS Calendar 측에서.
 */
export default function SchedulePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-5 py-8">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">직원 일정</h1>
        <p className="text-sm text-zinc-500">
          외근·출장·휴가 일정은 NAVER WORKS Calendar의 회사 공유 캘린더에서
          확인합니다.
        </p>
      </div>

      <a
        href="https://calendar.worksmobile.com/"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-3 text-sm font-medium text-white hover:bg-emerald-500"
      >
        🗓️ NAVER WORKS Calendar 열기 ↗
      </a>

      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300">
        <p className="mb-2 font-medium">사용 방법</p>
        <ul className="list-disc space-y-1 pl-5 text-xs text-zinc-600 dark:text-zinc-400">
          <li>
            <strong>등록·수정·삭제</strong>는 그대로 task.dyce.kr의 내 업무
            화면에서. 분류=외근/출장/휴가 또는 활동=외근/출장으로 task를
            만들면 자동으로 공유 캘린더에 반영됩니다.
          </li>
          <li>
            <strong>보기·알림</strong>은 NAVER WORKS Calendar에서. 회사 공유
            캘린더를 즐겨찾기 + 알림 ON으로 설정하면 본인 일정 알림을 받을 수
            있습니다.
          </li>
          <li>
            NAVER WORKS Calendar에서 직접 수정한 내용은 task.dyce.kr에 반영되지
            않습니다 (단방향 동기화). 수정은 항상 task.dyce.kr에서.
          </li>
        </ul>
      </div>
    </div>
  );
}
