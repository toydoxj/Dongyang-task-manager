"""/api/projects — read는 mirror, write는 노션 + write-through."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
from app.models.auth import User
from app.models.project import (
    Project,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectUpdateRequest,
    project_create_to_props,
    project_update_to_props,
)
from app.security import get_current_user
from app.services import notion_props as P
from app.services.mirror_dto import project_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/projects", tags=["projects"])


# ── 담당 변경 이력 (write-only, 노션 기록) ──


async def _log_assign_change(
    notion: NotionService,
    *,
    project_id: str,
    project_name: str,
    actor: str,
    target: str,
    action: str,
) -> None:
    db_id = get_settings().notion_db_assign_log
    if not db_id:
        return
    title = f"{action} · {target} · {project_name}"[:200]
    props = {
        "이벤트": {"title": [{"text": {"content": title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "작업": {"select": {"name": action}},
        "대상 담당자": {"rich_text": [{"text": {"content": target}}]},
        "변경자": {"rich_text": [{"text": {"content": actor}}]},
    }
    try:
        await notion.create_page(db_id, props)
    except Exception:  # noqa: BLE001
        pass


# ── mirror 기반 이름 해결 ──


def _resolve_names(db: Session, projects: list[Project]) -> None:
    """mirror_clients / mirror_master_projects에서 이름을 조회해 채운다."""
    if not projects:
        return
    client_ids: set[str] = {
        rid for p in projects for rid in p.client_relation_ids if rid
    }
    master_ids: set[str] = {p.master_project_id for p in projects if p.master_project_id}

    client_map: dict[str, str] = {}
    if client_ids:
        rows = db.execute(
            select(M.MirrorClient.page_id, M.MirrorClient.name).where(
                M.MirrorClient.page_id.in_(client_ids)
            )
        ).all()
        client_map = {pid: name for pid, name in rows}

    master_map: dict[str, str] = {}
    if master_ids:
        rows = db.execute(
            select(M.MirrorMaster.page_id, M.MirrorMaster.name).where(
                M.MirrorMaster.page_id.in_(master_ids)
            )
        ).all()
        master_map = {pid: name for pid, name in rows}

    for p in projects:
        if p.client_relation_ids:
            p.client_names = [
                client_map.get(rid, "") for rid in p.client_relation_ids if client_map.get(rid)
            ]
        if p.master_project_id:
            p.master_project_name = master_map.get(p.master_project_id, "")


# ── 라우터 ──


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    assignee: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    team: str | None = Query(default=None),
    completed: bool | None = Query(default=None),
    mine: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectListResponse:
    if mine:
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    stmt = select(M.MirrorProject).where(M.MirrorProject.archived.is_(False))
    if assignee:
        stmt = stmt.where(M.MirrorProject.assignees.any(assignee))  # type: ignore[attr-defined]
    if stage:
        stmt = stmt.where(M.MirrorProject.stage == stage)
    if team:
        stmt = stmt.where(M.MirrorProject.teams.any(team))  # type: ignore[attr-defined]
    if completed is not None:
        stmt = stmt.where(M.MirrorProject.completed.is_(completed))
    stmt = stmt.order_by(M.MirrorProject.code.asc())
    rows = db.execute(stmt).scalars().all()
    items = [project_from_mirror(r) for r in rows]
    _resolve_names(db, items)
    return ProjectListResponse(items=items, count=len(items))


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    for_user: str | None = Query(
        default=None,
        description="admin/team_lead가 다른 직원 명의로 프로젝트 생성 시 사용",
    ),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    db_id = get_settings().notion_db_projects
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_PROJECTS 미설정",
        )
    if not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="프로젝트명 필수"
        )
    # for_user 지정 시: 그 사람을 자동 담당자로. 권한 체크.
    target_name = user.name
    if for_user:
        if user.role not in {"admin", "team_lead"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="다른 직원 명의 생성은 관리자/팀장만 가능합니다",
            )
        target_name = for_user
    if target_name and target_name not in body.assignees:
        body = body.model_copy(update={"assignees": [*body.assignees, target_name]})

    page = await notion.create_page(db_id, project_create_to_props(body))
    get_sync().upsert_page("projects", page)
    return Project.from_notion_page(page)


@router.get("/{page_id}", response_model=Project)
async def get_project(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    row = db.get(M.MirrorProject, page_id)
    if row is not None and not row.archived:
        project = project_from_mirror(row)
        _resolve_names(db, [project])
        return project
    # mirror miss → 노션 fallback + upsert
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("projects", page)
    project = Project.from_notion_page(page)
    _resolve_names(db, [project])
    return project


@router.post("/{page_id}/assign", response_model=Project)
async def assign_me(
    page_id: str,
    set_to_waiting: bool = Query(
        default=False,
        description="True면 진행단계가 '진행중'이 아닐 때 '대기'로 변경 (가져오기 시 사용)",
    ),
    for_user: str | None = Query(
        default=None,
        description="admin/team_lead가 다른 직원을 담당자로 추가할 때 사용",
    ),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    # for_user 지정 시 권한 체크
    target_name: str
    if for_user:
        if user.role not in {"admin", "team_lead"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="다른 직원 대리 담당은 관리자/팀장만 가능합니다",
            )
        target_name = for_user
    else:
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않습니다",
            )
        target_name = user.name

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    props = page.get("properties", {})
    current = P.multi_select_names(props, "담당자")
    current_stage = P.select_name(props, "진행단계")
    needs_assign = target_name not in current
    needs_stage = set_to_waiting and current_stage != "진행중"

    if not needs_assign and not needs_stage:
        return Project.from_notion_page(page)

    update_props: dict = {}
    if needs_assign:
        new_assignees = current + [target_name]
        update_props["담당자"] = {
            "multi_select": [{"name": n} for n in new_assignees]
        }
    if needs_stage:
        update_props["진행단계"] = {"select": {"name": "대기"}}

    updated = await notion.update_page(page_id, update_props)
    get_sync().upsert_page("projects", updated)
    project = Project.from_notion_page(updated)
    if needs_assign:
        await _log_assign_change(
            notion,
            project_id=page_id,
            project_name=project.name,
            actor=user.name or "(시스템)",
            target=target_name,
            action="담당 추가",
        )
    return project


@router.patch("/{page_id}", response_model=Project)
async def update_project(
    page_id: str,
    body: ProjectUpdateRequest,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """프로젝트 부분 갱신 (편집 모달용)."""
    props = project_update_to_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="갱신할 필드가 없습니다"
        )
    try:
        page = await notion.update_page(page_id, props)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("projects", page)
    return Project.from_notion_page(page)


VALID_STAGES = {"진행중", "대기", "보류", "완료", "타절", "종결", "이관"}


@router.patch("/{page_id}/stage", response_model=Project)
async def set_project_stage(
    page_id: str,
    stage: str = Query(..., description="대기/보류/완료/타절/종결/이관 중 하나"),
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """대시보드 칸반 드래그용 — '진행중'은 자동 결정이라 강제 변경 불가."""
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"잘못된 stage: {stage}")
    if stage == "진행중":
        raise HTTPException(
            status_code=400,
            detail="'진행중'은 금주 TASK 활동으로 자동 결정됩니다. 수동 변경 불가",
        )
    try:
        page = await notion.update_page(
            page_id, {"진행단계": {"select": {"name": stage}}}
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("projects", page)
    return Project.from_notion_page(page)


@router.delete("/{page_id}/assign", response_model=Project)
async def unassign_me(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    if not user.name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="본인 이름이 등록되어 있지 않습니다",
        )
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc

    current = P.multi_select_names(page.get("properties", {}), "담당자")
    if user.name not in current:
        return Project.from_notion_page(page)

    new_assignees = [n for n in current if n != user.name]
    updated = await notion.update_page(
        page_id,
        {"담당자": {"multi_select": [{"name": n} for n in new_assignees]}},
    )
    get_sync().upsert_page("projects", updated)
    project = Project.from_notion_page(updated)
    await _log_assign_change(
        notion,
        project_id=page_id,
        project_name=project.name,
        actor=user.name,
        target=user.name,
        action="담당 제거",
    )
    return project


# ── 진행단계 자동 sync (mirror_tasks 기반으로 N+1 제거) ──


def _this_week_range() -> tuple[date, date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


@router.post("/{page_id}/sync-stage", response_model=Project)
async def sync_stage_by_tasks(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """진행중/대기 외 단계는 수동 설정 존중. mirror_tasks 단일 쿼리로 판단."""
    proj = db.get(M.MirrorProject, page_id)
    if proj is None or proj.archived:
        raise HTTPException(status_code=404, detail="프로젝트 미존재 (mirror)")
    if proj.stage not in ("진행중", "대기"):
        return project_from_mirror(proj)

    monday, sunday = _this_week_range()
    has_active = (
        db.execute(
            select(M.MirrorTask.page_id)
            .where(
                M.MirrorTask.project_ids.any(page_id),  # type: ignore[attr-defined]
                M.MirrorTask.archived.is_(False),
                or_(
                    # 기간이 금주에 걸침
                    (M.MirrorTask.start_date <= sunday)
                    & (M.MirrorTask.end_date >= monday),
                    # 또는 실제 완료일이 금주
                    (M.MirrorTask.actual_end_date >= monday)
                    & (M.MirrorTask.actual_end_date <= sunday),
                ),
            )
            .limit(1)
        ).first()
        is not None
    )
    desired = "진행중" if has_active else "대기"
    if desired == proj.stage:
        return project_from_mirror(proj)

    updated = await notion.update_page(
        page_id, {"진행단계": {"select": {"name": desired}}}
    )
    get_sync().upsert_page("projects", updated)
    return Project.from_notion_page(updated)
