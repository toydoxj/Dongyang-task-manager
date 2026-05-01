"""/api/projects — read는 mirror, write는 노션 + write-through."""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

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
from app.security import get_current_user, require_admin
from app.services import notion_props as P
from app.services import sso_drive
from app.services.mirror_dto import project_from_mirror
from app.services.notion import NotionService, get_notion
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
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """admin이 누락된/실패한 WORKS Drive 폴더 생성을 다시 시도.

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
    needs_clear_completed = needs_stage and current_completed

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
        # 가져오기로 다시 활성화 — '완료' 표시·'완료일'도 함께 해제
        # (mine list filter가 !completed 라 안 풀면 me 페이지에 안 보임).
        # 이전 완료일은 별도 assign log에 보존되어 기록 사라지지 않음.
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


# ── WORKS Drive 임베디드 파일 탐색기 ──


def _extract_resource_key(drive_url: str) -> str:
    """drive_url의 query string에서 resourceKey 추출 (= NAVER WORKS Drive root fileId)."""
    if not drive_url:
        return ""
    try:
        qs = parse_qs(urlparse(drive_url).query)
    except Exception:  # noqa: BLE001
        return ""
    v = qs.get("resourceKey")
    return v[0] if v else ""


class DriveItemDTO(BaseModel):
    fileId: str
    fileName: str
    fileType: str  # FOLDER | DOC | IMAGE | VIDEO | AUDIO | ZIP | EXE | ETC
    fileSize: int = 0
    modifiedTime: str = ""
    webUrl: str = ""


class DriveChildrenResponse(BaseModel):
    items: list[DriveItemDTO]
    next_cursor: str = ""


@router.get("/{page_id}/drive/children", response_model=DriveChildrenResponse)
async def list_drive_children(
    page_id: str,
    folder_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveChildrenResponse:
    """프로젝트 폴더(또는 그 sub 폴더)의 children list. 임베디드 탐색기용.

    folder_id 미지정 시 프로젝트 root 폴더 (drive_url의 resourceKey).
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")

    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)

    parent_id = folder_id or _extract_resource_key(project.drive_url)
    if not parent_id:
        raise HTTPException(
            status_code=422,
            detail="Drive 폴더가 아직 생성되지 않았습니다 (drive_url 없음)",
        )

    try:
        body: dict[str, Any] = await sso_drive.list_children(parent_id)
    except sso_drive.DriveError as e:
        # 401·token 만료는 sso_drive 내부에서 retry. 그래도 실패면 502.
        raise HTTPException(status_code=502, detail=str(e)) from e

    files = body.get("files") or []
    items: list[DriveItemDTO] = []
    for f in files:
        loc = f.get("resourceLocation")
        items.append(
            DriveItemDTO(
                fileId=str(f.get("fileId") or ""),
                fileName=str(f.get("fileName") or ""),
                fileType=str(f.get("fileType") or "ETC"),
                fileSize=int(f.get("fileSize") or 0),
                modifiedTime=str(f.get("modifiedTime") or ""),
                webUrl=sso_drive.build_file_web_url(
                    str(f.get("fileId") or ""), loc
                ),
            )
        )
    meta = body.get("responseMetaData") or {}
    return DriveChildrenResponse(
        items=items, next_cursor=str(meta.get("nextCursor") or "")
    )


class DriveStreamTokenResponse(BaseModel):
    token: str
    expires_in: int = 300


_STREAM_TOKEN_TTL = 300  # 5분


def _issue_drive_stream_token(
    file_id: str, user_id: int, jwt_secret: str
) -> str:
    """Drive streaming endpoint 인증용 short-lived JWT.

    URL query로 노출되어도 5분 TTL + file_id 고정이라 재사용 위험 적음.
    """
    payload = {
        "fid": file_id,
        "uid": user_id,
        "scope": "drive_stream",
        "exp": int(time.time()) + _STREAM_TOKEN_TTL,
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def _verify_drive_stream_token(token: str, jwt_secret: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=401, detail="invalid stream token") from e
    if payload.get("scope") != "drive_stream":
        raise HTTPException(status_code=401, detail="wrong scope")
    return payload


@router.get(
    "/{page_id}/drive/issue-token/{file_id}",
    response_model=DriveStreamTokenResponse,
)
async def issue_drive_stream_token(
    page_id: str,
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveStreamTokenResponse:
    """Drive 파일 stream용 short-lived JWT 발급."""
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    if db.get(M.MirrorProject, page_id) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    token = _issue_drive_stream_token(file_id, user.id, s.jwt_secret)
    return DriveStreamTokenResponse(token=token, expires_in=_STREAM_TOKEN_TTL)


@router.get("/{page_id}/drive/stream/{file_id}")
async def stream_drive_file(
    page_id: str,
    file_id: str,
    token: str = Query(..., description="issue-token으로 발급한 JWT"),
    file_name: str | None = Query(default=None, alias="name"),
) -> StreamingResponse:
    """short-lived token으로 인증, NAVER WORKS Drive에서 파일 stream을 받아
    그대로 forward. 모든 파일을 attachment로 강제 다운로드.

    httpx의 cross-domain redirect는 default로 Authorization 헤더를 strip하므로
    event_hook으로 매 outbound request에 Bearer 재부착 (apis-storage.worksmobile.com에서
    401 발생 방지).
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    payload = _verify_drive_stream_token(token, s.jwt_secret)
    if payload.get("fid") != file_id:
        raise HTTPException(status_code=401, detail="token/file_id mismatch")

    sd = s.works_drive_sharedrive_id
    if not sd:
        raise HTTPException(status_code=503, detail="WORKS_DRIVE_SHAREDRIVE_ID 미설정")

    bearer = await sso_drive._get_valid_access_token(s)
    upstream_url = (
        f"{s.works_api_base.rstrip('/')}"
        f"/sharedrives/{sd}/files/{file_id}/download"
    )

    async def _attach_bearer(request: httpx.Request) -> None:
        request.headers["Authorization"] = f"Bearer {bearer}"

    client = httpx.AsyncClient(
        timeout=600.0,
        follow_redirects=True,
        event_hooks={"request": [_attach_bearer]},
    )
    try:
        resp = await client.send(
            client.build_request("GET", upstream_url),
            stream=True,
        )
    except Exception:
        await client.aclose()
        raise

    if resp.status_code >= 400:
        body = await resp.aread()
        await client.aclose()
        logger.warning(
            "drive stream upstream %s: %s", resp.status_code, body[:300]
        )
        raise HTTPException(
            status_code=502, detail=f"upstream {resp.status_code}"
        )

    # 모든 파일을 attachment로 강제 다운로드 (Office protocol/inline 등 분기 폐기).
    # 사용자가 OS 다운로드 폴더에서 더블클릭 → OS 기본 앱(Office/한글/AutoCAD 등) 자동 launch.
    # NOTE: HTTP 헤더는 latin-1만 허용 → 한글 파일명은 RFC 5987 filename*=UTF-8'' 형식으로
    # percent-encoded ASCII로 변환 후 전송. filename(legacy)도 같은 percent-encoded 사용.
    forward_headers: dict[str, str] = {
        "content-type": resp.headers.get("content-type", "application/octet-stream"),
    }
    if "content-length" in resp.headers:
        forward_headers["content-length"] = resp.headers["content-length"]
    safe_name = (file_name or "").replace('"', "").replace("\\", "")
    if safe_name:
        from urllib.parse import quote

        encoded = quote(safe_name, safe="")
        forward_headers["content-disposition"] = (
            f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
        )
    else:
        forward_headers["content-disposition"] = "attachment"

    async def _aclose() -> None:
        await resp.aclose()
        await client.aclose()

    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers=forward_headers,
        background=BackgroundTask(_aclose),
    )


class DriveUploadResultItem(BaseModel):
    fileName: str
    fileId: str = ""
    fileSize: int = 0
    fileType: str = "ETC"
    webUrl: str = ""
    error: str = ""


class DriveUploadResponse(BaseModel):
    items: list[DriveUploadResultItem]


@router.post(
    "/{page_id}/drive/upload", response_model=DriveUploadResponse
)
async def upload_drive_files(
    page_id: str,
    files: list[UploadFile] = File(...),
    folder_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveUploadResponse:
    """드래그&드롭으로 들어온 파일 N개를 NAVER WORKS Drive 폴더에 업로드.

    folder_id가 비면 프로젝트 root 폴더. suffixOnDuplicate=true이므로 이름 충돌 시
    NAVER가 자동 번호 추가. 일부 실패는 result.error로 보고하고 다른 파일은 계속 진행.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")

    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)

    parent_id = folder_id or _extract_resource_key(project.drive_url)
    if not parent_id:
        raise HTTPException(
            status_code=422, detail="Drive 폴더가 아직 생성되지 않았습니다"
        )

    results: list[DriveUploadResultItem] = []
    for upload in files:
        name = upload.filename or "untitled"
        try:
            content = await upload.read()
            meta = await sso_drive.upload_file(
                parent_id,
                name,
                content,
                content_type=upload.content_type or None,
                settings=s,
            )
            file_id = str(meta.get("fileId") or "")
            results.append(
                DriveUploadResultItem(
                    fileName=str(meta.get("fileName") or name),
                    fileId=file_id,
                    fileSize=int(meta.get("fileSize") or len(content)),
                    fileType=str(meta.get("fileType") or "ETC"),
                    webUrl=sso_drive.build_file_web_url(
                        file_id, meta.get("resourceLocation")
                    ),
                )
            )
        except sso_drive.DriveError as e:
            logger.warning("파일 업로드 실패 %s: %s", name, e)
            results.append(
                DriveUploadResultItem(fileName=name, error=str(e))
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("파일 업로드 중 예외 %s", name)
            results.append(
                DriveUploadResultItem(fileName=name, error=f"내부 오류: {e}")
            )
    return DriveUploadResponse(items=results)
