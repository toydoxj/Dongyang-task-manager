import { describe, expect, it } from "vitest";

import type { Project, Task } from "@/lib/domain";

import {
  scheduleBucketForTask,
  scheduleWindowFor,
  shouldShowInScheduleTab,
  splitByThisWeek,
} from "./_utils";

function task(overrides: Partial<Task>): Task {
  return {
    id: "task-1",
    title: "일정",
    code: "",
    project_ids: [],
    sales_ids: [],
    status: "진행 중",
    progress: null,
    start_date: null,
    end_date: null,
    actual_end_date: null,
    priority: "보통",
    difficulty: "중간",
    category: "프로젝트",
    activity: "사무실",
    assignees: [],
    teams: [],
    note: "",
    weekly_plan_text: "",
    created_time: null,
    last_edited_time: null,
    url: null,
    ...overrides,
  };
}

function project(id: string): Project {
  return {
    id,
    code: "",
    master_code: "",
    master_project_id: "",
    master_project_name: "",
    name: id,
    client_text: "",
    client_relation_ids: [],
    client_names: [],
    stage: "진행중",
    phase: "",
    contract_signed: false,
    completed: false,
    start_date: null,
    contract_start: null,
    contract_end: null,
    end_date: null,
    assignees: [],
    teams: [],
    work_types: [],
    contract_amount: null,
    vat: null,
    method_review_fee: null,
    progress_payment: null,
    outsourcing_estimated: null,
    collection_rate: null,
    collection_total: null,
    expense_total: null,
    last_edited_time: null,
    url: null,
    drive_url: "",
  };
}

describe("scheduleBucketForTask", () => {
  it("휴가 옛 표기와 새 표기를 같은 버킷으로 묶는다", () => {
    expect(scheduleBucketForTask(task({ category: "휴가" }))).toBe("휴가");
    expect(scheduleBucketForTask(task({ category: "휴가(연차)" }))).toBe("휴가");
  });

  it("활동 기준 외근/출장/파견을 일정 버킷으로 판정한다", () => {
    expect(scheduleBucketForTask(task({ activity: "외근" }))).toBe("외근");
    expect(scheduleBucketForTask(task({ activity: "출장" }))).toBe("출장");
    expect(scheduleBucketForTask(task({ activity: "파견" }))).toBe("파견");
  });
});

describe("shouldShowInScheduleTab", () => {
  const window = scheduleWindowFor(new Date(2026, 4, 29));

  it("최근/다가오는 일정만 일정 탭에 표시한다", () => {
    expect(
      shouldShowInScheduleTab(
        task({ activity: "외근", start_date: "2026-05-15" }),
        window,
      ),
    ).toBe(true);
    expect(
      shouldShowInScheduleTab(
        task({ activity: "외근", start_date: "2026-07-28" }),
        window,
      ),
    ).toBe(true);
    expect(
      shouldShowInScheduleTab(
        task({ activity: "외근", start_date: "2026-05-14" }),
        window,
      ),
    ).toBe(false);
    expect(
      shouldShowInScheduleTab(
        task({ activity: "외근", start_date: "2026-07-29" }),
        window,
      ),
    ).toBe(false);
  });

  it("일정 분류가 아니면 표시하지 않는다", () => {
    expect(
      shouldShowInScheduleTab(
        task({ category: "개인업무", activity: "사무실" }),
        window,
      ),
    ).toBe(false);
  });
});

describe("splitByThisWeek", () => {
  it("dash 유무가 다른 project id도 금주 활동 프로젝트로 묶는다", () => {
    const p = project("1234-5678");
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;

    const result = splitByThisWeek(
      [p, project("idle-project")],
      [task({ project_ids: ["12345678"], start_date: today, end_date: today })],
    );

    expect(result.active.map((item) => item.id)).toEqual(["1234-5678"]);
    expect(result.idle.map((item) => item.id)).toEqual(["idle-project"]);
  });
});
