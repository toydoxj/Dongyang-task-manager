"""프로젝트 도메인 aggregate — stage_projects / completed / new_projects.

PR-DL (Phase 4-J 22단계): weekly_report/__init__.py에서 분리.

| 함수 | 출력 | cutoff |
|---|---|---|
| `aggregate_stage_projects` | `list[StageProjectItem]` | stage 매칭 (cutoff 없음). 대기만 한정 시 90일 stale flag |
| `aggregate_completed` | `list[CompletedProjectItem]` | `Project.end_date(완료일)` ∈ [last_week_start, last_week_end] |
| `aggregate_new_projects` | `list[NewProjectItem]` | `Project.start_date(수주일)` ∈ 같은 범위 |

세 함수 모두 MirrorProject + helpers(`_client_name_lookup`/`_resolve_client_label`)
공통 의존. `_TERMINATED_STAGES` 상수는 aggregate_completed 단독 사용 → 동반 이동.

Model(`StageProjectItem`/`CompletedProjectItem`/`NewProjectItem`)은 __init__.py에
잔류, build_weekly_report 직전 import. PR-DI/DJ/DK 검증 패턴.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.services.mirror_dto import project_from_mirror
from app.services.weekly_report import (
    CompletedProjectItem,
    NewProjectItem,
    StageProjectItem,
)
from app.services.weekly_report.helpers import (
    _client_name_lookup,
    _resolve_client_label,
    _scale_text,
)

_TERMINATED_STAGES = frozenset({"종결", "타절"})


def aggregate_stage_projects(
    db: Session,
    stages: list[str],
    *,
    exclude_ids: set[str] | None = None,
) -> list[StageProjectItem]:
    """주어진 stage들에 속한 active 프로젝트 list — cutoff 없음.

    컬럼: CODE / 용역명 / 발주처 / 담당팀. 정렬: 담당팀 → CODE.
    is_long_stalled: 대기(stages가 ['대기']에 한정)일 때만 의미 — last_edited_time이
    90일 전 이상이면 True (3개월 이상 활동 없음, 사용자 결정 2026-05-10).
    exclude_ids에 들어있는 page_id는 결과에서 제외.
    """
    excl = exclude_ids or set()
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .filter(M.MirrorProject.stage.in_(stages))
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    long_stall_threshold = datetime.now(timezone.utc) - timedelta(days=90)
    is_waiting_only = stages == ["대기"]
    items: list[StageProjectItem] = []
    for r in rows:
        if r.page_id in excl:
            continue
        if not r.name and not r.code:
            continue
        proj = project_from_mirror(r)
        is_long = (
            is_waiting_only
            and r.last_edited_time is not None
            and r.last_edited_time < long_stall_threshold
        )
        items.append(
            StageProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                client=_resolve_client_label(proj, client_name_by_id),
                teams=list(r.teams or []),
                is_long_stalled=is_long,
            )
        )
    # 정렬: 담당팀 → CODE (팀 미지정은 마지막)
    items.sort(key=lambda x: (x.teams[0] if x.teams else "￿", x.code))
    return items


def aggregate_completed(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[CompletedProjectItem]:
    """완료 프로젝트 — Project.end_date(노션 "완료일")가 저번주 범위 안.

    기준 (사용자 결정 2026-05-09):
    - 완료일(end_date)이 [last_week_start, last_week_end] 안
    - completed=True 또는 stage in {종결, 타절} (운영자가 명시적으로 표시한 것)
    - 완료일 비어있는 row는 제외 (운영자가 노션 "완료일" 입력 안 한 경우 표시 X)
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(
            or_(
                M.MirrorProject.completed.is_(True),
                M.MirrorProject.stage.in_(_TERMINATED_STAGES),
            )
        )
        .order_by(M.MirrorProject.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()
    items: list[CompletedProjectItem] = []
    for r in rows:
        proj = project_from_mirror(r)
        ed = (proj.end_date or "")[:10]
        if not ed or not (range_start_iso <= ed <= range_end_iso):
            continue
        label = r.stage if r.stage in _TERMINATED_STAGES else "완료"
        # 소요기간(개월) — 시작일 ~ 완료일 (start, end 모두 있을 때만 계산)
        duration_months: float | None = None
        sd = (proj.start_date or "")[:10]
        if sd and ed:
            try:
                d_sd = date.fromisoformat(sd)
                d_ed = date.fromisoformat(ed)
                duration_months = round((d_ed - d_sd).days / 30.0, 1)
            except ValueError:
                duration_months = None
        items.append(
            CompletedProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                teams=list(r.teams or []),
                assignees=list(r.assignees or []),
                client=_resolve_client_label(proj, client_name_by_id),
                status_label=label,
                completed_at=proj.end_date,
                started_at=proj.start_date,
                duration_months=duration_months,
            )
        )
    return items


def aggregate_new_projects(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[NewProjectItem]:
    """신규 프로젝트 — 저번주 범위 내 수주된 프로젝트.

    기준: 노션 "시작일"(수주확정일) = Project.start_date가 [last_week_start, last_week_end]
    범위 안. completed=False (이미 완료된 건 제외 — 완료 표에 별도 표시).
    이전 stage 휴리스틱(_NEW_STAGES) 폐기 — mirror_projects.stage가 운영상태(진행중/대기/보류)라
    작업단계 가정이 맞지 않았음 (사용자 피드백 2026-05-09).
    """
    rows = (
        db.query(M.MirrorProject)
        .filter(M.MirrorProject.archived.is_(False))
        .filter(M.MirrorProject.completed.is_(False))
        .order_by(M.MirrorProject.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()

    # 영업 → 프로젝트 변환된 경우 sales의 규모(연면적/층수) lookup
    sales_by_converted_pid: dict[str, M.MirrorSales] = {
        s.converted_project_id: s
        for s in db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(M.MirrorSales.converted_project_id != "")
        .all()
    }

    items: list[NewProjectItem] = []
    for r in rows:
        proj = project_from_mirror(r)
        sd = (proj.start_date or "")[:10]  # YYYY-MM-DD prefix만
        # 시작일이 저번주 범위 안에 있어야 신규 — 문자열 비교(ISO 형식이라 안전)
        if not sd or not (range_start_iso <= sd <= range_end_iso):
            continue
        sale = sales_by_converted_pid.get(r.page_id)
        scale = _scale_text(sale) if sale else ""
        items.append(
            NewProjectItem(
                page_id=r.page_id,
                code=r.code,
                name=r.name,
                teams=list(r.teams or []),
                assignees=list(r.assignees or []),
                client=_resolve_client_label(proj, client_name_by_id),
                work_types=list(proj.work_types or []),
                scale=scale,
                contract_amount=proj.contract_amount,
                stage=r.stage,
                started_at=proj.start_date,
            )
        )
    return items
