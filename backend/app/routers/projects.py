"""/api/projects — 노션 메인 프로젝트 DB 조회 라우터."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.exceptions import NotFoundError
from app.models.auth import User
from app.models.project import (
    Project,
    ProjectCreateRequest,
    ProjectListResponse,
    project_create_to_props,
)
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

# 발주처(협력업체) DB — 메인 프로젝트의 "발주처" relation이 가리킴
# 주의: query_all 은 database id 를 받음 (data_source id 가 아님)
_CLIENT_DB_ID = "307e84986c8680f197eed98407eabf84"

router = APIRouter(prefix="/projects", tags=["projects"])


async def _log_assign_change(
    notion: NotionService,
    *,
    project_id: str,
    project_name: str,
    actor: str,
    target: str,
    action: str,  # "담당 추가" | "담당 제거"
) -> None:
    """담당자 변경 이력을 노션 DB에 기록 (실패해도 main 작업은 계속)."""
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
    except Exception:  # noqa: BLE001 — 로그 실패는 main 작업 막지 않음
        pass


async def _resolve_client_names(
    notion: NotionService, projects: list[Project]
) -> None:
    """모든 프로젝트의 client_relation_ids 를 일괄로 이름 매핑."""
    has_relations = any(p.client_relation_ids for p in projects)
    if not has_relations:
        return
    try:
        title_map = await notion.fetch_title_dict(_CLIENT_DB_ID)
    except Exception:
        return
    for p in projects:
        if p.client_relation_ids:
            p.client_names = [
                title_map.get(rid, "") for rid in p.client_relation_ids if title_map.get(rid)
            ]


def _build_filter(
    *,
    assignee: str | None,
    stage: str | None,
    team: str | None,
    completed: bool | None,
) -> dict[str, Any] | None:
    """노션 filter 표현식 합성. 없으면 None."""
    clauses: list[dict[str, Any]] = []
    if assignee:
        clauses.append(
            {"property": "담당자", "multi_select": {"contains": assignee}}
        )
    if stage:
        clauses.append({"property": "진행단계", "select": {"equals": stage}})
    if team:
        clauses.append({"property": "담당팀", "multi_select": {"contains": team}})
    if completed is not None:
        clauses.append({"property": "완료", "checkbox": {"equals": completed}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"and": clauses}


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    assignee: str | None = Query(default=None, description="담당자명"),
    stage: str | None = Query(default=None, description="진행단계"),
    team: str | None = Query(default=None, description="담당팀"),
    completed: bool | None = Query(default=None, description="완료 여부"),
    mine: bool = Query(default=False, description="True면 본인 담당만 (assignee 무시)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> ProjectListResponse:
    db_id = get_settings().notion_db_projects
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_PROJECTS 미설정",
        )

    if mine:
        # 본인 이름이 노션 담당자 옵션에 등록되어 있다고 가정 (User.name 사용)
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    filt = _build_filter(
        assignee=assignee, stage=stage, team=team, completed=completed
    )
    sorts = [{"property": "Sub_CODE", "direction": "ascending"}]
    pages = await notion.query_all(db_id, filter=filt, sorts=sorts)
    items = [Project.from_notion_page(p) for p in pages]
    await _resolve_client_names(notion, items)
    return ProjectListResponse(items=items, count=len(items))


@router.post("", response_model=Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreateRequest,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """노션 메인 프로젝트 DB에 새 페이지 생성. 본인을 자동 담당자로 추가."""
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
    # 본인 자동 담당 추가 (중복 방지)
    if user.name and user.name not in body.assignees:
        body = body.model_copy(update={"assignees": [*body.assignees, user.name]})

    page = await notion.create_page(db_id, project_create_to_props(body))
    return Project.from_notion_page(page)


@router.get("/{page_id}", response_model=Project)
async def get_project(
    page_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    project = Project.from_notion_page(page)
    await _resolve_client_names(notion, [project])
    return project


@router.post("/{page_id}/assign", response_model=Project)
async def assign_me(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """현재 로그인 사용자를 프로젝트 담당자에 추가 (이미 있으면 no-op)."""
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
    if user.name in current:
        return Project.from_notion_page(page)

    new_assignees = current + [user.name]
    updated = await notion.update_page(
        page_id,
        {"담당자": {"multi_select": [{"name": n} for n in new_assignees]}},
    )
    project = Project.from_notion_page(updated)
    await _log_assign_change(
        notion,
        project_id=page_id,
        project_name=project.name,
        actor=user.name,
        target=user.name,
        action="담당 추가",
    )
    return project


@router.delete("/{page_id}/assign", response_model=Project)
async def unassign_me(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """현재 로그인 사용자를 프로젝트 담당자에서 제거."""
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
