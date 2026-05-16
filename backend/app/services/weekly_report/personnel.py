"""인원 도메인 aggregate — 인원현황 + 팀원 명단.

PR-DK (Phase 4-J 21단계): weekly_report/__init__.py에서 분리.

| 함수 | 출력 | 의존 |
|---|---|---|
| `aggregate_headcount` | `HeadcountSummary` | Employee + `_classify_occupation` (helpers) |
| `aggregate_team_members` | `dict[str, list[TeamMember]]` | Employee |

두 함수 모두 Employee 모델을 동일 조건(resigned_at 미설정 또는 week_end 이후)으로
필터링한다. 같은 도메인에 묶음.

Model(`HeadcountSummary` / `TeamMember`)은 `__init__.py`에 그대로 두고 import.
build_weekly_report 직전에 본 모듈을 import하므로 partial loading 시점에
attribute가 확보된 상태(PR-DI/DJ 검증 패턴).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.services.weekly_report import HeadcountSummary, TeamMember
from app.services.weekly_report.helpers import _classify_occupation


def aggregate_headcount(db: Session, week_start: date, week_end: date) -> HeadcountSummary:
    """재직자 수 + 직종/팀별 분포 + 주간 신규/퇴사."""
    # 재직 = resigned_at is None or resigned_at > week_end (퇴사일이 이번 주 이후면 아직 재직)
    rows = (
        db.query(Employee)
        .filter(or_(Employee.resigned_at.is_(None), Employee.resigned_at > week_end))
        .all()
    )
    by_occ: dict[str, int] = defaultdict(int)
    by_team: dict[str, int] = defaultdict(int)
    for e in rows:
        by_occ[_classify_occupation(e.team, e.position)] += 1
        if e.team:
            by_team[e.team] += 1

    # 이번 주 신규 (created_at은 datetime, KST 자정 기준)
    new_count = (
        db.query(Employee)
        .filter(Employee.created_at >= datetime.combine(week_start, time.min))
        .filter(Employee.created_at <= datetime.combine(week_end, time.max))
        .count()
    )

    # 이번 주 퇴사
    resigned_rows = (
        db.query(Employee.name)
        .filter(Employee.resigned_at >= week_start)
        .filter(Employee.resigned_at <= week_end)
        .all()
    )

    return HeadcountSummary(
        total=len(rows),
        by_occupation=dict(by_occ),
        by_team=dict(by_team),
        new_this_week=new_count,
        resigned_this_week=[r[0] for r in resigned_rows],
    )


def aggregate_team_members(
    db: Session, week_end: date
) -> dict[str, list[TeamMember]]:
    """팀별 재직 직원 명단 — 개인일정 grid에서 빈 칸이라도 행이 보이도록.

    재직 = resigned_at IS NULL or resigned_at > week_end (주차 안에 퇴사한 사람도
    표시). 팀별로 sort_order → 이름 정렬. 팀이 비어있는 직원은 제외.
    """
    rows = (
        db.query(Employee)
        .filter(or_(Employee.resigned_at.is_(None), Employee.resigned_at > week_end))
        .all()
    )
    by_team: dict[str, list[TeamMember]] = defaultdict(list)
    for e in rows:
        team = (e.team or "").strip()
        if not team:
            continue
        by_team[team].append(
            TeamMember(
                name=e.name,
                position=e.position or "",
                team=team,
                sort_order=e.sort_order or 0,
            )
        )
    for members in by_team.values():
        members.sort(key=lambda m: (m.sort_order, m.name))
    return dict(by_team)
