"""주간 업무일지 작은 helper + 모듈 상수.

PR-DI/2 (Phase 4-J 19단계): weekly_report/__init__.py에서 분리.

| 종류 | 목록 |
|---|---|
| 상수 | `_KST`, `_OCCUPATION_RULES`, `_SCHEDULE_TEXT_CATEGORIES` |
| pure helper | `_classify_occupation`, `_kst_range`, `_client_name`, `_scale_text`, `_resolve_client_label`, `_relation_column`, `_vacation_label`, `_normalize_schedule_category` |
| DB session helper | `_client_name_lookup`, `_avg_task_progress` |

큰 helper(`_employee_last_week_done` / `_employee_this_week_plan` /
`_project_weekly_plans` ~280줄)는 차기 PR(team aggregate)에서 함께 이동.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models import mirror as M

if TYPE_CHECKING:
    from app.models.project import Project


_KST = timezone(timedelta(hours=9))

# 직종 분류 휴리스틱 — employees.team 또는 position에서 추출.
# 명확한 매핑 테이블이 없으므로 prefix/keyword 매칭.
_OCCUPATION_RULES = (
    ("구조설계", ("구조1팀", "구조2팀", "구조3팀", "구조4팀", "구조설계")),
    ("안전진단", ("진단팀", "안전진단")),
    ("관리세무", ("관리팀", "세무팀", "관리세무", "총무")),
)

_SCHEDULE_TEXT_CATEGORIES = frozenset(
    {"외근", "출장", "교육", "연차", "반차", "파견", "동행"}
)


def _classify_occupation(team: str, position: str) -> str:
    """employees.team / position을 직종 라벨로 매핑. 미매칭은 '기타'."""
    blob = f"{team} {position}".strip()
    for label, keywords in _OCCUPATION_RULES:
        if any(k in blob for k in keywords):
            return label
    return "기타"


def _kst_range(week_start: date, week_end: date | None = None) -> tuple[datetime, datetime]:
    """[week_start KST 00:00, week_end KST 23:59:59.999999) UTC aware datetime.

    week_end가 None이면 월~금(default = week_start + 4일).
    """
    if week_start.weekday() != 0:
        raise ValueError(f"week_start must be Monday, got {week_start.isoformat()} ({week_start.strftime('%A')})")
    end = week_end if week_end is not None else (week_start + timedelta(days=4))
    start_local = datetime.combine(week_start, time.min, tzinfo=_KST)
    end_local = datetime.combine(end, time.max, tzinfo=_KST)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _client_name(props: dict[str, Any]) -> str:
    """프로젝트 properties에서 발주처 이름 휴리스틱 추출 — 임시 텍스트 우선."""
    p = props or {}
    txt = p.get("발주처(임시)", {})
    if isinstance(txt, dict):
        rt = txt.get("rich_text") or []
        if rt and isinstance(rt[0], dict):
            return rt[0].get("plain_text") or rt[0].get("text", {}).get("content") or ""
    return ""


def _scale_text(sale: M.MirrorSales) -> str:
    """영업 row의 규모 표기 — '44,594.71㎡ / 지하6층, 지상12층 / 3동' 형식."""
    parts: list[str] = []
    if sale.gross_floor_area:
        parts.append(f"{sale.gross_floor_area:,.2f}㎡")
    floors: list[str] = []
    if sale.floors_below:
        floors.append(f"지하{int(sale.floors_below)}층")
    if sale.floors_above:
        floors.append(f"지상{int(sale.floors_above)}층")
    if floors:
        parts.append(", ".join(floors))
    if sale.building_count:
        parts.append(f"{int(sale.building_count)}동")
    return " / ".join(parts)


def _client_name_lookup(db: Session) -> dict[str, str]:
    """mirror_clients의 (page_id → name) 딕셔너리 — 발주처 relation 이름 해결.

    노션 프로젝트의 "발주처" relation은 거래처 DB의 page_id를 가리킨다. mirror_dto의
    Project.client_text는 "발주처(임시)" rich_text fallback 컬럼이라 비어있는 경우가
    많고, 정식 발주처는 client_relation_ids → mirror_clients 조회가 필요.
    """
    return {
        c.page_id: c.name or ""
        for c in db.query(M.MirrorClient.page_id, M.MirrorClient.name).all()
    }


def _resolve_client_label(
    proj: "Project", client_name_by_id: dict[str, str]
) -> str:
    """발주처 relation 이름 우선 → 임시 텍스트 fallback."""
    for cid in proj.client_relation_ids:
        name = client_name_by_id.get(cid, "").strip()
        if name:
            return name
    return proj.client_text or ""


def _avg_task_progress(db: Session, project_id: str) -> float:
    """프로젝트에 속한 active task들의 progress 평균. mirror_projects에 진행률 컬럼 부재 대응."""
    rows = (
        db.query(M.MirrorTask.progress)
        .filter(
            M.MirrorTask.archived.is_(False),
            M.MirrorTask.project_ids.any(project_id),
            M.MirrorTask.progress.isnot(None),
        )
        .all()
    )
    vals = [r[0] for r in rows if r[0] is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _relation_column(kind: str):  # noqa: ANN201 — return SQLAlchemy column
    """kind='project' → MirrorTask.project_ids, 'sale' → sales_ids."""
    if kind == "sale":
        return M.MirrorTask.sales_ids
    return M.MirrorTask.project_ids


def _vacation_label(task: M.MirrorTask) -> str:
    """휴가 task → 라벨. 우선순위: task 제목 키워드 > duration fallback.

    사용자 요청(2026-05-10): 일률 "연차"가 아니라 제목에 명시된 표현 그대로
    표시. 운영자가 "오전반차" / "오후반차" / "반차" / "연차" 등 자유 입력 가능.
    제목에 키워드가 없으면 duration ≥ 4h '연차', < 4h '반차'로 fallback.
    """
    title = (task.title or "").strip()
    # '반차' 통합 표기 — '오전반차' / '오후반차' 모두 '반차'로 단일화
    if "반차" in title:
        return "반차"
    if "연차" in title:
        return "연차"
    period = (task.properties or {}).get("기간", {}).get("date") or {}
    start_iso = period.get("start") or ""
    end_iso = period.get("end") or ""
    if "T" not in start_iso or not end_iso or "T" not in end_iso:
        return "연차"
    try:
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError:
        return "연차"
    hours = (end_dt - start_dt).total_seconds() / 3600
    return "연차" if hours >= 4.0 else "반차"


def _normalize_schedule_category(task: M.MirrorTask) -> str:
    """schedule 매트릭스 표시용 category 라벨 정규화.

    사용자 결정(2026-05-10): 텍스트는 일정성 카테고리만 표시.
    "프로젝트"/"영업(서비스)" 같은 업무 분류는 적지 않고 activity(외근/출장) 사용.

    - "휴가" / "휴가(연차)" → duration 기반 "연차"(≥4h) 또는 "반차"(<4h)
    - 일정성 카테고리(_SCHEDULE_TEXT_CATEGORIES) → 그대로
    - 그 외(프로젝트/영업/개인업무/사내잡무 등) → task.activity (외근/출장)
    - 둘 다 없으면 빈 문자열 (호출자가 skip)
    """
    cat = task.category or ""
    if cat in ("휴가", "휴가(연차)"):
        return _vacation_label(task)
    if cat in _SCHEDULE_TEXT_CATEGORIES:
        return cat
    return task.activity or ""
