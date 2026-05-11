"use client";

/**
 * 주간 업무일지 미리보기 본체 — PDF 양식과 1:1 통일된 dumb component.
 * 모든 계산 결과는 부모(WeeklyReportPage)가 props로 전달.
 *
 * PR-AJ — app/weekly-report/page.tsx에서 추출.
 */

import type {
  WeeklyHoliday,
  WeeklyPersonalScheduleEntry,
  WeeklyReport,
} from "@/lib/api";

import { ProjectLink, SaleLink } from "./links";
import { BulletList, Section, SimpleTable } from "./primitives";
import { ScheduleTeamCard } from "./ScheduleMini";
import { SplitStageGrid } from "./StageTables";
import { TeamWorkTable } from "./TeamWorkTable";

/** 개인일정 grid에서 5팀 column 표시 순서 (본부는 5번째 column 끝에 별도 stack). */
const SCHEDULE_GRID_TEAMS = ["구조1팀", "구조2팀", "구조3팀", "구조4팀", "진단팀"] as const;
const SCHEDULE_EXTRA_TEAM = "본부";

interface PreviewProps {
  data: WeeklyReport;
  teamWorkNames: string[];
  scheduleByEmployee: Record<string, WeeklyPersonalScheduleEntry[][]>;
  weekDays: { iso: string; label: string }[];
  holidayByIso: Record<string, WeeklyHoliday[]>;
}

export default function ReportPreview({
  data,
  teamWorkNames,
  scheduleByEmployee,
  weekDays,
  holidayByIso,
}: PreviewProps) {
  const period = `${data.period_start} ~ ${data.period_end}`;
  return (
    <div className="weekly-report-tables space-y-4">
      {/* PDF 헤더 양식 동등 — 좌측 제목/기간, 우측 회사명 */}
      <div className="flex items-end justify-between gap-3 border-b-2 border-emerald-600/70 pb-1">
        <div className="text-lg font-bold tracking-wide">
          주간업무일지
          <span className="ml-2 text-sm font-medium text-zinc-500">{period}</span>
        </div>
        <div className="text-right leading-tight">
          <div className="text-sm font-bold text-zinc-700 dark:text-zinc-200">
            (주)동양구조
          </div>
          <div className="text-[9px] font-bold tracking-tighter text-zinc-500">
            Dongyang Consulting Engineers. Co., Ltd.
          </div>
        </div>
      </div>

      {/* 1. 인원현황 — PDF와 동일: 구조설계/안전진단/관리 순서 + 총원 = 3개 합계 (기타 제외).
          구조설계 = 노션 '구조설계' + 1, 관리 = 노션 '관리세무' + 1. */}
      <Section title="인원현황" id="headcount" badge="auto" sourceHref="/admin/employees">
        {(() => {
          const sDesign = (data.headcount.by_occupation["구조설계"] ?? 0) + 1;
          const sInspect = data.headcount.by_occupation["안전진단"] ?? 0;
          const sOffice = (data.headcount.by_occupation["관리세무"] ?? 0) + 1;
          const totalDisplay = sDesign + sInspect + sOffice;
          return (
            <div className="rounded border border-zinc-200 bg-zinc-50 p-2 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              총원 <strong>{totalDisplay}</strong>인
              <span className="text-zinc-600 dark:text-zinc-400">
                <span className="mx-1 text-zinc-400">│</span>구조설계 {sDesign}
              </span>
              <span className="text-zinc-600 dark:text-zinc-400">
                <span className="mx-1 text-zinc-400">│</span>안전진단 {sInspect}
              </span>
              <span className="text-zinc-600 dark:text-zinc-400">
                <span className="mx-1 text-zinc-400">│</span>관리 {sOffice}
              </span>
              {(data.headcount.new_this_week > 0 ||
                data.headcount.resigned_this_week.length > 0) && (
                <>
                  <span className="mx-2 text-zinc-400">│</span>
                  <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-700">
                    변동
                  </span>{" "}
                  신규 {data.headcount.new_this_week}
                  {data.headcount.resigned_this_week.length > 0 && (
                    <span className="text-red-600 dark:text-red-400">
                      {" "}
                      / 퇴사 {data.headcount.resigned_this_week.length} (
                      {data.headcount.resigned_this_week.join(", ")})
                    </span>
                  )}
                </>
              )}
              {data.holidays.length > 0 && (
                <>
                  <span className="mx-2 text-zinc-400">│</span>
                  <span className="rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-700">
                    공휴일
                  </span>{" "}
                  {data.holidays
                    .map(
                      (h) =>
                        `${h.date.slice(5).replace("-", "/")} ${h.name}${
                          h.source === "company" ? "(사내)" : ""
                        }`,
                    )
                    .join(" · ")}
                </>
              )}
            </div>
          );
        })()}
      </Section>

      {/* 2. 공지/교육/건의 — 3-col grid */}
      <div id="manual-section" className="grid gap-3 md:grid-cols-3">
        <Section title="주요 공지사항" badge="manual" sourceHref="/admin/notices">
          {data.notices.length > 0 ? (
            <BulletList items={data.notices} />
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
        <Section title="교육 일정" badge="manual" sourceHref="/admin/notices">
          {data.education.length > 0 ? (
            <BulletList items={data.education} />
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
        <Section title="건의사항" badge="manual" sourceHref="/suggestions">
          {data.suggestions.length > 0 ? (
            <ul className="list-inside list-disc space-y-0.5 text-sm">
              {data.suggestions.map((s, i) => (
                <li key={i}>
                  {s.title}
                  <span className="ml-1 text-[10px] text-zinc-500">
                    · {s.author} · {s.status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-zinc-500">(없음)</p>
          )}
        </Section>
      </div>

      {/* 3. 개인 주간 일정 — 5팀 horizontal grid (본부는 진단팀 column 끝에 stack) */}
      <Section title="개인 주간 일정" id="personal-schedule" badge="auto" sourceHref="/schedule">
        <div className="grid gap-2 lg:grid-cols-5">
          {SCHEDULE_GRID_TEAMS.map((team) => (
            <ScheduleTeamCard
              key={team}
              team={team}
              members={data.team_members[team] ?? []}
              scheduleByEmployee={scheduleByEmployee}
              weekDays={weekDays}
              holidayByIso={holidayByIso}
              extra={
                team === "진단팀"
                  ? {
                      title: SCHEDULE_EXTRA_TEAM,
                      members: data.team_members[SCHEDULE_EXTRA_TEAM] ?? [],
                    }
                  : undefined
              }
            />
          ))}
        </div>
        {data.holidays.length > 0 && (
          <p className="text-[10px] text-zinc-500">
            ※ 공휴일:{" "}
            {data.holidays
              .map(
                (h) =>
                  `${h.date.slice(5)} ${h.name}${
                    h.source === "company" ? "(사내)" : ""
                  }`,
              )
              .join(" · ")}
          </p>
        )}
      </Section>

      {/* 4. 신규 프로젝트 */}
      <Section title="신규 프로젝트" id="new-projects" badge="auto" sourceHref="/projects">
        <SimpleTable
          cols={["업무내용", "CODE", "용역명", "발주처", "규모", "용역비"]}
          rows={data.new_projects.map((n) => [
            n.work_types.join("/"),
            n.code,
            <ProjectLink key="n" id={n.page_id}>{n.name}</ProjectLink>,
            n.client,
            n.scale,
            n.contract_amount ? `₩${n.contract_amount.toLocaleString()}` : "",
          ])}
          empty="(신규 없음)"
        />
      </Section>

      {/* 5. 완료 프로젝트 */}
      <Section title="완료 프로젝트" id="completed" badge="auto" sourceHref="/projects">
        <SimpleTable
          cols={["상태", "CODE", "프로젝트명", "발주처", "담당팀", "소요기간(개월)"]}
          rows={data.completed.map((c) => [
            c.status_label,
            c.code,
            <ProjectLink key="n" id={c.page_id}>{c.name}</ProjectLink>,
            c.client,
            c.teams.join(", "),
            c.duration_months != null ? c.duration_months.toFixed(1) : "",
          ])}
          empty="(완료 없음)"
        />
      </Section>

      {/* 6. 날인대장 */}
      <Section title="날인대장" id="seal-ledger" badge="auto" sourceHref="/seal-requests">
        <SimpleTable
          cols={["승인일", "CODE", "용역명", "제출처", "유형", "담당자"]}
          rows={data.seal_log.map((s) => [
            (s.approved_at ?? "").slice(5, 10).replace("-", "/"),
            s.code,
            <ProjectLink key="n" id={s.project_id}>{s.name}</ProjectLink>,
            s.submission_target,
            s.seal_type,
            s.requester,
          ])}
          empty="(저번주 승인된 날인 없음)"
        />
      </Section>

      {/* 9. 영업 — PDF와 동일: 영업번호/PROJECT/발주처/규모/견적가/수주확률/비고 */}
      <Section title="영업" id="sales" badge="auto" sourceHref="/sales">
        <SimpleTable
          cols={[
            "영업번호",
            "PROJECT",
            "발주처",
            "규모",
            "견적가",
            "수주확률",
            "비고",
          ]}
          rows={data.sales.map((s) => [
            s.code,
            <SaleLink key="n" id={s.page_id}>{s.name}</SaleLink>,
            s.client,
            s.scale,
            s.estimated_amount
              ? `₩${s.estimated_amount.toLocaleString()}`
              : "",
            s.probability != null ? `${Math.round(s.probability)}%` : "",
            s.is_bid ? "(입찰)" : "",
          ])}
          empty="(저번주 시작 영업건 없음 — 노션 '영업시작일' 입력 필요)"
        />
      </Section>

      {/* 팀별 업무 현황 — 직원 × 프로젝트 행 단위 */}
      <Section title="팀별 업무 현황" id="team-work" badge="auto" sourceHref="/admin/employee-work">
        {teamWorkNames.length === 0 ? (
          <p className="text-xs text-zinc-500">(배정된 진행 프로젝트 없음)</p>
        ) : (
          <div className="space-y-3">
            {teamWorkNames.map((team) => (
              <TeamWorkTable
                key={team}
                team={team}
                rows={data.team_work[team]}
              />
            ))}
          </div>
        )}
      </Section>

      {/* 대기 프로젝트 — 자체 2-열 분할 (대기가 길어 보류와 같이 두면 비대칭) */}
      <Section title="대기 프로젝트" id="waiting" badge="auto" sourceHref="/projects">
        <SplitStageGrid rows={data.waiting_projects} highlightStalled />
      </Section>

      {/* 보류 프로젝트 — 자체 2-열 분할 */}
      <Section title="보류 프로젝트" id="on-hold" badge="auto" sourceHref="/projects">
        <SplitStageGrid rows={data.on_hold_projects} />
      </Section>
    </div>
  );
}
