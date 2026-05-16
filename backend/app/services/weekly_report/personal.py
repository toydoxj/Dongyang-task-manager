"""개인 일정(personal_schedule) aggregate.

PR-DM (Phase 4-J 23단계): weekly_report/__init__.py에서 분리.

직원×요일 매트릭스 — task.category가 일정성 카테고리 OR task.activity가
외근/출장/파견인 task만 추출. 일정 라벨은 helpers의 `_normalize_schedule_category`
에 위임 (휴가/연차/반차 분기 + activity fallback).

`_SCHEDULE_CATEGORIES` 상수는 본 aggregate 단독 사용 → 동반 이동 (모듈 응집도).
helpers의 `_SCHEDULE_TEXT_CATEGORIES`(연차/반차/외근/출장/교육/파견/동행)와는
별개 — 이쪽은 task.category 필터용(휴가/휴가(연차)/외근/출장/파견/교육).

Model(`PersonalScheduleEntry`)은 __init__.py 잔류, build_weekly_report 직전
import. PR-DI/DJ/DK/DL 검증 패턴.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.models.employee import Employee
from app.services.weekly_report import PersonalScheduleEntry
from app.services.weekly_report.helpers import _normalize_schedule_category

# 개인 일정 매트릭스에 표시할 task category.
# "휴가(연차)"는 frontend의 통합 옵션 — 표시 시 duration 기반 연차/반차로 분기.
# "외근/출장/파견"은 task.activity로도 표현 가능하므로 두 source 모두 lookup.
_SCHEDULE_CATEGORIES = frozenset(
    {"외근", "출장", "파견", "휴가", "휴가(연차)", "교육"}
)


def aggregate_personal_schedule(
    db: Session, week_start: date, week_end: date
) -> list[PersonalScheduleEntry]:
    """직원×요일 매트릭스.

    포함 조건: task.category가 일정성 카테고리 OR task.activity가 외근/출장/파견.
    (프로젝트 task가 분류='프로젝트'여도 활동이 외근/출장/파견이면 일정에 표시)
    """
    rows = (
        db.query(M.MirrorTask)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(
            or_(
                M.MirrorTask.category.in_(_SCHEDULE_CATEGORIES),
                M.MirrorTask.activity.in_({"외근", "출장", "파견"}),
            )
        )
        # 일정 구간 [start_date, end_date]가 [week_start, week_end]와 교집합
        .filter(or_(M.MirrorTask.start_date.is_(None), M.MirrorTask.start_date <= week_end))
        .filter(or_(M.MirrorTask.end_date.is_(None), M.MirrorTask.end_date >= week_start))
        .all()
    )
    # 직원별 team 조회 캐시
    team_by_name: dict[str, str] = {}
    for emp in db.query(Employee.name, Employee.team).all():
        team_by_name[emp.name] = emp.team or ""

    entries: list[PersonalScheduleEntry] = []
    for t in rows:
        label = _normalize_schedule_category(t)
        if not label:
            continue
        # task source 판정 — sales_ids 있으면 영업, project_ids 있으면 프로젝트, 그 외 기타
        if t.sales_ids:
            kind = "sale"
        elif t.project_ids:
            kind = "project"
        else:
            kind = "other"
        for assignee in t.assignees or []:
            entries.append(
                PersonalScheduleEntry(
                    employee_name=assignee,
                    team=team_by_name.get(assignee, ""),
                    category=label,
                    kind=kind,
                    start_date=(t.start_date or week_start).isoformat(),
                    end_date=(t.end_date or t.start_date or week_end).isoformat(),
                    note="",
                    project_code=(t.code or "")[:32],
                )
            )
    return entries
