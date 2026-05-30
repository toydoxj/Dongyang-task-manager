"""/api/projects — read는 mirror, write는 mirror direct + outbox enqueue.

PR-FS Phase 1.3.5: write 흐름이 노션 호출을 사용자 응답 path에서 제거.
mirror direct update + outbox enqueue 같은 transaction. drain worker가 background
에서 노션 push. _log_assign_change는 BackgroundTasks로 이관 — 사용자 응답 즉시.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

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
from app.models.notion_outbox import OP_UPDATE
from app.models.project import (
    PROJECT_COMPLETED_STAGES,
    Project,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectUpdateRequest,
    is_project_completed_stage,
    project_create_to_props,
    project_update_to_props,
)
from app.security import get_current_user, require_admin, require_editor
from app.services import notion_props as P
from app.services import sso_drive
from app.services.mirror_dto import project_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.notion_outbox import enqueue
from app.services.project_stage_sync import reconcile_project_stage
from app.services.sync import get_sync
from app.settings import get_settings


def _project_page_from_mirror_with_update(
    row: M.MirrorProject, update_props: dict
) -> dict:
    """mirror row + update_props 병합 → 노션 page-like dict (sync._upsert_project용).

    PR-FS Phase 1.3.5: write endpoint이 mirror direct update + outbox enqueue 시,
    mirror 정규화 필드 동기화를 sync._upsert_project로 재사용. 같은 패턴 PR-FR.
    """
    merged_props = {**(row.properties or {}), **update_props}
    return {
        "id": row.page_id,
        "properties": merged_props,
        "url": row.url or "",
        "created_time": None,  # MirrorProject에 created_time 없음 (last_edited만)
        "last_edited_time": datetime.now(timezone.utc).isoformat(),
        "archived": False,
    }

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
    if completed is True:
        stmt = stmt.where(M.MirrorProject.stage.in_(PROJECT_COMPLETED_STAGES))
    elif completed is False:
        stmt = stmt.where(~M.MirrorProject.stage.in_(PROJECT_COMPLETED_STAGES))
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

    # PR-FS: user_facing=True — 5초 deadline + SDK timeout 4s.
    page = await notion.create_page(
        db_id, project_create_to_props(body), user_facing=True
    )
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
) -> Project:
    """누락된/실패한 WORKS Drive 폴더 생성을 다시 시도.

    동기 호출 — 결과를 즉시 응답에 반영. idempotent라 폴더 있으면 URL만 다시 저장.

    PR-GB: 노션 update/get 제거 → mirror direct + outbox (PR-FS 패턴). WORKS Drive
    폴더 생성(sso_drive)은 외부 API라 동기 유지, 노션 URL 저장만 mirror-direct.
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
    if not url:
        return project  # 폴더는 확보됐으나 URL 미반환 — mirror 현재 상태 반환
    update_props: dict = {"WORKS Drive URL": {"url": url}}
    page_like = _project_page_from_mirror_with_update(row, update_props)
    sync = get_sync()
    sync.upsert_in_session(db, "projects", page_like)
    enqueue(
        db, aggregate_type="projects", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()
    return Project.from_notion_page(page_like)


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
    # mirror miss → 노션 fallback + upsert (PR-FS: user_facing=True)
    try:
        page = await notion.get_page(page_id, user_facing=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("projects", page)
    project = Project.from_notion_page(page)
    _resolve_names(db, [project])
    return project


@router.post("/{page_id}/assign", response_model=Project)
async def assign_me(
    page_id: str,
    background: BackgroundTasks,
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
    db: Session = Depends(get_db),
) -> Project:
    """PR-FS: mirror direct + outbox enqueue. _log_assign_change는 BackgroundTasks."""
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

    row = db.get(M.MirrorProject, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    props = row.properties or {}
    current = P.multi_select_names(props, "담당자")
    current_stage = P.select_name(props, "진행단계")
    current_completed = is_project_completed_stage(current_stage)
    prev_end_date = P.date_range(props, "완료일")[0] or ""
    needs_assign = target_name not in current
    needs_stage = set_to_waiting and current_stage != "진행중"
    needs_clear_completed = needs_stage and current_completed

    if not needs_assign and not needs_stage:
        return project_from_mirror(row)

    update_props: dict = {}
    if needs_assign:
        new_assignees = current + [target_name]
        update_props["담당자"] = {
            "multi_select": [{"name": n} for n in new_assignees]
        }
    if needs_stage:
        update_props["진행단계"] = {"select": {"name": "대기"}}
    if needs_clear_completed:
        update_props["완료일"] = {"date": None}

    page_like = _project_page_from_mirror_with_update(row, update_props)
    sync = get_sync()
    sync.upsert_in_session(db, "projects", page_like)
    enqueue(
        db, aggregate_type="projects", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()
    project = Project.from_notion_page(page_like)

    # assign log는 별도 노션 DB (mirror 없음) — BackgroundTasks로 이관.
    # 사용자 응답에 영향 없음. 노션 hang 시에도 응답 즉시.
    if needs_assign:
        background.add_task(
            _log_assign_change,
            notion,
            project_id=page_id,
            project_name=project.name,
            actor=user.name or "(시스템)",
            target=target_name,
            action="담당 추가",
        )
    if needs_clear_completed:
        background.add_task(
            _log_assign_change,
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
    notion: NotionService = Depends(get_notion),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> Project:
    """프로젝트 부분 갱신 (편집 모달용). admin/team_lead/manager.

    PR-FS: mirror direct + outbox enqueue. 사용자 응답 즉시 (~50ms baseline).
    """
    _ = notion  # signature backward compat
    props = project_update_to_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="갱신할 필드가 없습니다"
        )
    row = db.get(M.MirrorProject, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    page_like = _project_page_from_mirror_with_update(row, props)
    sync = get_sync()
    sync.upsert_in_session(db, "projects", page_like)
    enqueue(
        db, aggregate_type="projects", aggregate_id=page_id,
        op=OP_UPDATE, payload=props, notion_page_id=page_id,
    )
    db.commit()
    return Project.from_notion_page(page_like)


VALID_STAGES = {"진행중", "대기", "보류", "완료", "타절", "종결", "이관"}


@router.patch("/{page_id}/stage", response_model=Project)
async def set_project_stage(
    page_id: str,
    background: BackgroundTasks,
    stage: str = Query(..., description="대기/보류/완료/타절/종결/이관 중 하나"),
    _admin: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> Project:
    """대시보드 칸반 드래그용 — admin 전용. '진행중'은 자동 결정이라 강제 변경 불가.

    PR-FS: mirror direct + outbox enqueue.
    """
    _ = notion
    if stage not in VALID_STAGES:
        raise HTTPException(status_code=400, detail=f"잘못된 stage: {stage}")
    if stage == "진행중":
        raise HTTPException(
            status_code=400,
            detail="'진행중'은 금주 TASK 활동으로 자동 결정됩니다. 수동 변경 불가",
        )
    row = db.get(M.MirrorProject, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    was_completed = is_project_completed_stage(row.stage)
    will_be_completed = is_project_completed_stage(stage)
    prev_end_date = P.date_range(row.properties or {}, "완료일")[0] or ""
    props = {"진행단계": {"select": {"name": stage}}}
    if was_completed and not will_be_completed:
        props["완료일"] = {"date": None}
    page_like = _project_page_from_mirror_with_update(row, props)
    sync = get_sync()
    sync.upsert_in_session(db, "projects", page_like)
    enqueue(
        db, aggregate_type="projects", aggregate_id=page_id,
        op=OP_UPDATE, payload=props, notion_page_id=page_id,
    )
    db.commit()
    project = Project.from_notion_page(page_like)
    if was_completed and not will_be_completed:
        background.add_task(
            _log_assign_change,
            notion,
            project_id=page_id,
            project_name=(
                f"{project.name} (이전 완료일: {prev_end_date or '미상'})"
            ),
            actor=_admin.name or "(시스템)",
            target="(자동)",
            action="완료 해제",
        )
    return project


@router.delete("/{page_id}/assign", response_model=Project)
async def unassign_me(
    page_id: str,
    background: BackgroundTasks,
    for_user: str | None = Query(
        default=None,
        description="admin/team_lead가 다른 직원의 담당을 해제할 때 사용",
    ),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> Project:
    """PR-FS: mirror direct + outbox enqueue. _log_assign_change BackgroundTasks."""
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

    row = db.get(M.MirrorProject, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

    current = P.multi_select_names(row.properties or {}, "담당자")
    if target_name not in current:
        return project_from_mirror(row)

    new_assignees = [n for n in current if n != target_name]
    update_props = {"담당자": {"multi_select": [{"name": n} for n in new_assignees]}}
    page_like = _project_page_from_mirror_with_update(row, update_props)
    sync = get_sync()
    sync.upsert_in_session(db, "projects", page_like)
    enqueue(
        db, aggregate_type="projects", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()
    project = Project.from_notion_page(page_like)
    background.add_task(
        _log_assign_change,
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
    # PR-FS: user_facing=True — 5초 wallclock budget. 노션 hang 시 fail-fast → 빈 응답.
    try:
        pages = await notion.query_all(
            db_id, filter=filt, sorts=sorts, user_facing=True
        )
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
