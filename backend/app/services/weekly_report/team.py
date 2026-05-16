"""팀별 업무 도메인 — team_projects / team_work + 보조 helper / 정렬 상수.

PR-DN (Phase 4-J 24단계, 4-J 마지막): weekly_report/__init__.py에서 분리.

가장 무거운 모듈 — `aggregate_team_work`은 mirror_tasks를 한 번에 fetch해
(relation_id, kind, employee) bucket으로 펼쳐 N+1을 회피한다(원본 32s → 0.8s).

| 함수 | 용도 |
|---|---|
| `aggregate_team_projects` | 팀별 진행 중 프로젝트 — 단순 SQL + per-project 진행률 평균 |
| `aggregate_team_work` | 팀별 (직원 × 프로젝트/영업) 행 — bulk pre-fetch + bucket 합산 |

동반 이동: 정렬 상수 `_ACTIVE_STAGES` / `_STAGE_SORT_PRIORITY` — team aggregate
단독 사용.

Model(`TeamProjectRow` / `EmployeeWorkRow`)은 __init__.py에 잔류, build_weekly_report
직전 import. PR-DI/DJ/DK/DL/DM 검증 패턴.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.models.employee import Employee
from app.services.mirror_dto import project_from_mirror
from app.services.weekly_report import EmployeeWorkRow, TeamProjectRow
from app.services.weekly_report.helpers import (
    _client_name_lookup,
    _resolve_client_label,
)

# 진행 중으로 간주할 stage (완료/타절/종결/이관 제외)
_ACTIVE_STAGES = frozenset({"진행중", "대기", "보류", "기본설계", "실시설계", "계획설계", "계획검토", "사업승인"})

# 팀별 표 내 정렬 우선순위 (사용자 결정 2026-05-09): 진행중 → 대기 → 보류 → 그 외.
# "기본설계/실시설계" 등 작업단계는 진행중 그룹으로 묶어 가장 위에 표시.
_STAGE_SORT_PRIORITY: dict[str, int] = {
    "진행중": 1,
    "기본설계": 1,
    "실시설계": 1,
    "계획설계": 1,
    "계획검토": 1,
    "사업승인": 1,
    "대기": 2,
    "보류": 3,
}


def aggregate_team_projects(
    db: Session, week_start: date, week_end: date
) -> dict[str, list[TeamProjectRow]]:
    """팀별 진행 중 프로젝트 — completed=False, stage가 active.

    Bulk pre-fetch: mirror_tasks를 한 번에 가져와 진행률 평균/금주예정사항을
    메모리에서 계산 (N+1 제거).
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .order_by(M.MirrorProject.code)
        .all()
    )
    # 한 번에 모든 active project의 task fetch — project_id 별로 메모리 그룹.
    task_rows = (
        db.query(
            M.MirrorTask.project_ids,
            M.MirrorTask.progress,
            M.MirrorTask.weekly_plan_text,
            M.MirrorTask.start_date,
            M.MirrorTask.end_date,
        )
        .filter(M.MirrorTask.archived.is_(False))
        .all()
    )
    progress_by_pid: dict[str, list[float]] = defaultdict(list)
    plans_by_pid: dict[str, list[str]] = defaultdict(list)
    for pids, prog, plan, sd, ed in task_rows:
        if not pids:
            continue
        # 이번주와 교집합 task만 weekly_plan 후보
        in_this_week = (sd is None or sd <= week_end) and (
            ed is None or ed >= week_start
        )
        plan_norm = (plan or "").strip()
        for pid in pids:
            if prog is not None:
                progress_by_pid[pid].append(prog)
            if in_this_week and plan_norm:
                plans_by_pid[pid].append(plan_norm)

    client_name_by_id = _client_name_lookup(db)
    by_team: dict[str, list[TeamProjectRow]] = defaultdict(list)
    for r in rows:
        if r.stage and r.stage not in _ACTIVE_STAGES:
            continue
        teams = [t for t in (r.teams or []) if t]
        if not teams:
            continue
        proj = project_from_mirror(r)
        plans = plans_by_pid.get(r.page_id, [])
        # 중복 제거 (순서 유지)
        seen: set[str] = set()
        plans_uniq: list[str] = []
        for p in plans:
            if p not in seen:
                seen.add(p)
                plans_uniq.append(p)
        progs = progress_by_pid.get(r.page_id, [])
        progress = sum(progs) / len(progs) if progs else 0.0
        assignees = list(r.assignees or [])
        row = TeamProjectRow(
            code=r.code,
            name=r.name,
            client=_resolve_client_label(proj, client_name_by_id),
            pm=assignees[0] if assignees else "",
            stage=r.stage,
            progress=progress,
            weekly_plan=" · ".join(plans_uniq),
            note="",
            assignees=assignees,
            end_date=proj.end_date or proj.contract_end,
        )
        for team in teams:
            by_team[team].append(row)

    # 팀 내 정렬: 진행중 → 대기 → 보류 → 그 외 (secondary: code)
    for team_rows in by_team.values():
        team_rows.sort(
            key=lambda x: (_STAGE_SORT_PRIORITY.get(x.stage, 99), x.code)
        )
    return dict(by_team)


def aggregate_team_work(
    db: Session,
    week_start: date,
    week_end: date,
    last_week_start: date,
    last_week_end: date,
) -> dict[str, list[EmployeeWorkRow]]:
    """팀별 (직원 × 프로젝트/영업) 행 단위 업무 현황 — PDF 일지 본래 양식.

    Bulk pre-fetch 방식 (성능 최적화):
    - mirror_tasks를 한 번에 fetch 후 메모리에서 (relation_id, kind, employee)로 bucket
    - mirror_projects/sales/clients/employees도 각 1회 fetch
    - row 후보는 bucket 키 — last_week 또는 this_week가 있는 (relation, employee) 쌍만
      펼쳐서 빈 row 자동 제거

    그룹 기준: 직원의 employees.team. 팀 소속 없는 직원(사장 등) 행 제외.
    팀 내 정렬: 직원 sort_order → 이름 → 단계 우선순위 → relation code.
    """

    # ── 1. 직원 lookup ──
    emp_meta: dict[str, tuple[str, str, int]] = {}
    for emp in db.query(
        Employee.name, Employee.position, Employee.team, Employee.sort_order
    ).all():
        emp_meta[emp.name] = (emp.position or "", emp.team or "", emp.sort_order or 0)

    # ── 2. mirror_projects / mirror_sales meta dict ──
    project_rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .all()
    )
    project_meta: dict[str, M.MirrorProject] = {}
    for r in project_rows:
        if r.stage and r.stage not in _ACTIVE_STAGES:
            continue
        project_meta[r.page_id] = r

    sales_rows = (
        db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(~M.MirrorSales.stage.in_(["수주확정", "실주", "취소", "전환완료", "종결"]))
        .all()
    )
    sales_meta: dict[str, M.MirrorSales] = {s.page_id: s for s in sales_rows}

    client_name_by_id = _client_name_lookup(db)

    # ── 3. 관련 task 한 번에 fetch (지난주 활성/완료 또는 이번주 활성) ──
    tasks = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                # 지난주에 완료된 task (actual_end_date 기준)
                and_(
                    M.MirrorTask.actual_end_date.isnot(None),
                    M.MirrorTask.actual_end_date >= last_week_start,
                    M.MirrorTask.actual_end_date <= last_week_end,
                ),
                # 지난주에 활성이었던 task — 기간이 last_week와 교집합 (진행 중 포함)
                and_(
                    or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= last_week_end),
                    or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= last_week_start),
                ),
                # 이번주 활성 task — 기간이 [week_start, week_end]와 교집합
                and_(
                    or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end),
                    or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start),
                ),
            )
        )
        .all()
    )

    # ── 4. (relation_id, kind, employee) bucket ──
    # value: (last_week_titles, this_week_plans, this_week_titles) — 모두 list (중복은 후처리)
    Bucket = dict[tuple[str, str, str], dict[str, list[str]]]
    buckets: Bucket = defaultdict(
        lambda: {"last": [], "this_plans": [], "this_titles": []}
    )
    for t in tasks:
        title = (t.title or "").strip()
        plan = (t.weekly_plan_text or "").strip()
        # 지난주 활성: actual_end가 last_week 안 (완료) OR task 기간이 last_week와 교집합 (진행 중 포함)
        is_last_week = (
            t.actual_end_date is not None
            and last_week_start <= t.actual_end_date <= last_week_end
        ) or (
            (t.start_date is None or t.start_date <= last_week_end)
            and (t.end_date is None or t.end_date >= last_week_start)
        )
        is_this_week = (t.start_date is None or t.start_date <= week_end) and (
            t.end_date is None or t.end_date >= week_start
        )
        relations: list[tuple[str, str]] = []
        for pid in t.project_ids or []:
            relations.append((pid, "project"))
        for sid in t.sales_ids or []:
            relations.append((sid, "sale"))
        if not relations:
            continue
        for assignee in t.assignees or []:
            for rid, kind in relations:
                key = (rid, kind, assignee)
                if is_last_week and title:
                    buckets[key]["last"].append(title)
                if is_this_week:
                    if plan:
                        buckets[key]["this_plans"].append(plan)
                    if title:
                        buckets[key]["this_titles"].append(title)

    # ── 5. row 생성 (빈 row 자동 제거 — bucket에 있는 키만) ──
    def _join_unique(items: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for s in items:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return " · ".join(out)

    by_team: dict[str, list[EmployeeWorkRow]] = defaultdict(list)
    for (rid, kind, assignee), data in buckets.items():
        position, emp_team, _ = emp_meta.get(assignee, ("", "", 0))
        if not emp_team:
            continue
        last = _join_unique(data["last"])
        this_plans = _join_unique(data["this_plans"])
        this_titles = _join_unique(data["this_titles"])
        # weekly_plan_text 우선, 없으면 활성 task title
        this = this_plans or this_titles
        if not last and not this:
            continue
        if kind == "project":
            p = project_meta.get(rid)
            if p is None:
                continue
            proj = project_from_mirror(p)
            client = _resolve_client_label(proj, client_name_by_id)
            row = EmployeeWorkRow(
                employee_name=assignee,
                position=position,
                kind="project",
                source_id=p.page_id,
                project_code=p.code,
                project_name=p.name,
                client=client,
                stage=p.stage,  # 운영 — 정렬용
                phase=proj.phase,  # 작업단계 — UI 표시
                last_week_summary=last,
                this_week_plan=this,
                note="",
            )
        else:  # kind == "sale"
            s = sales_meta.get(rid)
            if s is None:
                continue
            sale_client = ""
            if s.client_id:
                sale_client = (client_name_by_id.get(s.client_id) or "").strip()
            row = EmployeeWorkRow(
                employee_name=assignee,
                position=position,
                kind="sale",
                source_id=s.page_id,
                project_code=s.code,
                project_name=s.name,
                client=sale_client,
                stage=f"영업·{s.stage}" if s.stage else "영업",
                phase="영업",  # 영업은 작업단계 대신 라벨 고정
                last_week_summary=last,
                this_week_plan=this,
                note="",
            )
        by_team[emp_team].append(row)

    # 팀 내 정렬
    for team_rows in by_team.values():
        team_rows.sort(
            key=lambda x: (
                emp_meta.get(x.employee_name, ("", "", 9999))[2],
                x.employee_name,
                _STAGE_SORT_PRIORITY.get(x.stage, 99),
                x.project_code,
            )
        )
    return dict(by_team)
