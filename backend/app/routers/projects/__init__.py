"""/api/projects — read는 mirror, write는 노션 + write-through."""
from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel
from sqlalchemy import func, select
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
from app.security import get_current_user, require_admin, require_editor
from app.services import notion_props as P
from app.services import sso_drive
from app.services.mirror_dto import project_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.project_stage_sync import reconcile_project_stage
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("projects")
router = APIRouter(prefix="/projects", tags=["projects"])


# ── WORKS Drive 폴더 자동 provisioning ──


async def _provision_drive_folder(
    notion: NotionService, page_id: str, code: str, name: str
) -> None:
    """Drive 폴더 생성 + 노션 'WORKS Drive URL' 갱신 + mirror 갱신.

    background task로 호출. 모든 예외를 catch 해 본 흐름에 영향 X.
    code/name이 없으면 skip.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        return
    if not (code or "").strip() or not (name or "").strip():
        return
    try:
        _fid, url = await sso_drive.ensure_project_folder(
            s, code=code, project_name=name
        )
    except sso_drive.DriveError as e:
        logger.warning("Drive 폴더 생성 실패 page=%s: %s", page_id, e)
        return
    except Exception:  # noqa: BLE001
        logger.exception("Drive 폴더 provisioning 중 예외 page=%s", page_id)
        return
    if not url:
        logger.info("Drive 폴더 생성됐으나 URL 응답 누락 page=%s", page_id)
        return
    try:
        await notion.update_page(
            page_id, properties={"WORKS Drive URL": {"url": url}}
        )
        updated = await notion.get_page(page_id)
        get_sync().upsert_page("projects", updated)
    except Exception:  # noqa: BLE001
        logger.exception("Drive URL 노션 저장 실패 page=%s", page_id)


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
    except Exception as e:  # noqa: BLE001 — 변경 이력 기록은 best-effort, 메인 흐름 차단 X
        # PR-BV (silent except 가시화): 변경 이력 page 생성 실패 운영 추적용
        logger.warning("프로젝트 담당 변경 이력 기록 실패: %s", e)


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


# PR-DC (Phase 4-J 13단계): sub-router include — 상위 router의 prefix(`/projects`)를
# 그대로 상속받음. sub-module은 prefix 없이 endpoint 정의.
from app.routers.projects import options as _options  # noqa: E402

router.include_router(_options.router)


# PR-DZ (4-C 1차): list_projects pagination. backward-compat 최우선 —
# offset/limit 미지정 시 기존 unbounded 동작 유지. 명시 시 max 500 cap.
# total 필드는 신규 클라이언트만 사용 (Optional).
_LIST_MAX_LIMIT = 500


@router.get("", response_model=ProjectListResponse)
def list_projects(
    assignee: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    team: str | None = Query(default=None),
    completed: bool | None = Query(default=None),
    mine: bool = Query(default=False),
    q: str | None = Query(default=None, description="code/name ILIKE 검색 (PR-ED 4-C)"),
    offset: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=_LIST_MAX_LIMIT),
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
        # contains(@>) — ARRAY GIN 인덱스 활용. .any() 는 GIN 미적용.
        stmt = stmt.where(M.MirrorProject.assignees.contains([assignee]))  # type: ignore[attr-defined]
    if stage:
        stmt = stmt.where(M.MirrorProject.stage == stage)
    if team:
        stmt = stmt.where(M.MirrorProject.teams.contains([team]))  # type: ignore[attr-defined]
    if completed is not None:
        stmt = stmt.where(M.MirrorProject.completed.is_(completed))
    if q:
        # PR-ED: code 또는 name에 부분 일치 (대소문자 무시).
        from sqlalchemy import or_ as _or

        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            _or(M.MirrorProject.code.ilike(pattern), M.MirrorProject.name.ilike(pattern))
        )
    # ORDER BY code ASC + page_id tie-breaker (Codex 권고: code 중복 가능성 대비
    # 결정론 보장). page_id는 노션 UUID라 사실상 unique.
    stmt = stmt.order_by(M.MirrorProject.code.asc(), M.MirrorProject.page_id.asc())

    # pagination — offset/limit 명시되면 적용 + total 채움. 미지정이면 unbounded.
    paged = offset is not None or limit is not None
    total: int | None = None
    if paged:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(db.execute(count_stmt).scalar() or 0)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().all()
    items = [project_from_mirror(r) for r in rows]
    _resolve_names(db, items)
    return ProjectListResponse(items=items, count=len(items), total=total)


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    background: BackgroundTasks,
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
    # Drive 폴더 자동 생성 (실패해도 응답엔 영향 없음)
    background.add_task(
        _provision_drive_folder, notion, page.get("id"), body.code, body.name
    )
    return Project.from_notion_page(page)


@router.post("/{page_id}/works-drive", response_model=Project)
async def retry_works_drive(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """누락된/실패한 WORKS Drive 폴더 생성을 다시 시도.

    동기 호출 — 결과를 즉시 응답에 반영. idempotent라 폴더 있으면 URL만 다시 저장.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")

    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)
    if not project.code or not project.name:
        raise HTTPException(
            status_code=400, detail="code/name이 비어있어 폴더 생성 불가"
        )
    try:
        _fid, url = await sso_drive.ensure_project_folder(
            s, code=project.code, project_name=project.name
        )
    except sso_drive.DriveError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    if url:
        await notion.update_page(
            page_id, properties={"WORKS Drive URL": {"url": url}}
        )
    page = await notion.get_page(page_id)
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
    current_completed = P.checkbox(props, "완료")
    prev_end_date = P.date_range(props, "완료일")[0] or ""
    needs_assign = target_name not in current
    needs_stage = set_to_waiting and current_stage != "진행중"
    # 부정합 healing — stage가 활성(진행중/대기)인데 completed=true 면
    # 사용자가 '재활성화' 클릭한 의도가 완료 체크박스 클리어임. me 필터의
    # !p.completed 때문에 진행중 임에도 목록에서 안 보이는 갇힘 상태 해소.
    needs_data_heal = (
        current_stage in {"진행중", "대기"} and current_completed
    )
    needs_clear_completed = (needs_stage and current_completed) or needs_data_heal

    if not needs_assign and not needs_stage and not needs_data_heal:
        return Project.from_notion_page(page)

    update_props: dict = {}
    if needs_assign:
        new_assignees = current + [target_name]
        update_props["담당자"] = {
            "multi_select": [{"name": n} for n in new_assignees]
        }
    if needs_stage:
        update_props["진행단계"] = {"select": {"name": "대기"}}
    # 가져오기로 다시 활성화 — '완료' 표시·'완료일' 해제. 이전 완료일은
    # assign log 에 보존. needs_data_heal 케이스도 동일 처리.
    if needs_clear_completed:
        update_props["완료"] = {"checkbox": False}
        update_props["완료일"] = {"date": None}

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
    # 완료 해제(재활성화) 이벤트도 동일 assign log에 기록 — 이전 완료일 보존용
    if needs_clear_completed:
        await _log_assign_change(
            notion,
            project_id=page_id,
            project_name=(
                f"{project.name} (이전 완료일: {prev_end_date or '미상'})"
            ),
            actor=user.name or "(시스템)",
            target=target_name,
            action="완료 해제",
        )
    return project


@router.patch("/{page_id}", response_model=Project)
async def update_project(
    page_id: str,
    body: ProjectUpdateRequest,
    _user: User = Depends(require_editor),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """프로젝트 부분 갱신 (편집 모달용). admin/team_lead/manager."""
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
    _admin: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """대시보드 칸반 드래그용 — admin 전용. '진행중'은 자동 결정이라 강제 변경 불가."""
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
    for_user: str | None = Query(
        default=None,
        description="admin/team_lead가 다른 직원의 담당을 해제할 때 사용",
    ),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    # for_user 지정 시 권한 체크 (assign_me 와 대칭)
    target_name: str
    if for_user:
        if user.role not in {"admin", "team_lead"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="다른 직원 대리 담당해제는 관리자/팀장만 가능합니다",
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

    current = P.multi_select_names(page.get("properties", {}), "담당자")
    if target_name not in current:
        return Project.from_notion_page(page)

    new_assignees = [n for n in current if n != target_name]
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
        actor=user.name or "(시스템)",
        target=target_name,
        action="담당 제거",
    )
    return project


# ── 프로젝트 변경 이력(assign log) 조회 ──


class ProjectLogEntry(BaseModel):
    id: str
    event_at: str  # ISO datetime (노션 created_time)
    title: str
    action: str
    target: str
    actor: str


class ProjectLogResponse(BaseModel):
    items: list[ProjectLogEntry]
    count: int


@router.get("/{page_id}/log", response_model=ProjectLogResponse)
async def get_project_log(
    page_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> ProjectLogResponse:
    """assign log DB에서 그 프로젝트와 관련된 이벤트 시간순 반환."""
    db_id = get_settings().notion_db_assign_log
    if not db_id:
        return ProjectLogResponse(items=[], count=0)
    filt = {
        "property": "프로젝트",
        "relation": {"contains": page_id},
    }
    sorts = [{"timestamp": "created_time", "direction": "ascending"}]
    try:
        pages = await notion.query_all(db_id, filter=filt, sorts=sorts)
    except Exception:  # noqa: BLE001
        logger.exception("assign log 조회 실패 page_id=%s", page_id)
        return ProjectLogResponse(items=[], count=0)
    items: list[ProjectLogEntry] = []
    for p in pages:
        props = p.get("properties", {})
        items.append(
            ProjectLogEntry(
                id=p.get("id", ""),
                event_at=p.get("created_time", ""),
                title=P.title(props, "이벤트"),
                action=P.select_name(props, "작업"),
                target=P.rich_text(props, "대상 담당자"),
                actor=P.rich_text(props, "변경자"),
            )
        )
    return ProjectLogResponse(items=items, count=len(items))


# ── 진행단계 자동 sync (mirror_tasks 기반으로 N+1 제거) ──


@router.post("/{page_id}/sync-stage", response_model=Project)
async def sync_stage_by_tasks(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """진행중/대기 외 단계는 수동 설정 존중. helper로 위임."""
    proj = db.get(M.MirrorProject, page_id)
    if proj is None or proj.archived:
        raise HTTPException(status_code=404, detail="프로젝트 미존재 (mirror)")
    updated = await reconcile_project_stage(notion, page_id)
    if updated is None:
        return project_from_mirror(proj)
    # identity-map stale read 회피 — 노션 응답 page를 직접 변환
    return Project.from_notion_page(updated)



# PR-DD (Phase 4-J 14단계): WORKS Drive sub-router (review-folder + children +
# stream + upload + delete) — drive.py로 분리.
from app.routers.projects import drive as _drive  # noqa: E402

router.include_router(_drive.router)
