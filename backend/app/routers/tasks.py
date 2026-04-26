"""/api/tasks — 신규 통합 업무TASK DB CRUD."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.exceptions import NotFoundError
from app.models.auth import User
from app.models.task import (
    Task,
    TaskCreateRequest,
    TaskListResponse,
    TaskUpdateRequest,
    task_create_to_props,
    task_update_to_props,
)
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _build_filter(
    *,
    project_id: str | None,
    assignee: str | None,
    status_name: str | None,
) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []
    if project_id:
        clauses.append(
            {"property": "프로젝트", "relation": {"contains": project_id}}
        )
    if assignee:
        clauses.append(
            {"property": "담당자", "multi_select": {"contains": assignee}}
        )
    if status_name:
        clauses.append({"property": "상태", "status": {"equals": status_name}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"and": clauses}


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    project_id: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    status_name: str | None = Query(default=None, alias="status"),
    mine: bool = Query(default=False),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> TaskListResponse:
    db_id = get_settings().notion_db_tasks
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_TASKS 미설정",
        )
    if mine:
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    filt = _build_filter(
        project_id=project_id, assignee=assignee, status_name=status_name
    )
    pages = await notion.query_all(db_id, filter=filt)
    items = [Task.from_notion_page(p) for p in pages]
    return TaskListResponse(items=items, count=len(items))


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateRequest,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Task:
    db_id = get_settings().notion_db_tasks
    props = task_create_to_props(body)
    page = await notion.create_page(db_id, props)
    return Task.from_notion_page(page)


@router.get("/{page_id}", response_model=Task)
async def get_task(
    page_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Task:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return Task.from_notion_page(page)


@router.patch("/{page_id}", response_model=Task)
async def update_task(
    page_id: str,
    body: TaskUpdateRequest,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Task:
    props = task_update_to_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="갱신할 필드가 없습니다"
        )
    page = await notion.update_page(page_id, props)
    return Task.from_notion_page(page)


@router.delete("/{page_id}")
async def archive_task(
    page_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """노션은 영구 삭제 대신 archive 사용."""
    await notion.update_page(page_id, properties={})  # placeholder
    # archive: pages.update에는 없고, 별도 호출 필요
    # notion-client 3.x: client.pages.update(page_id, archived=True)
    # 단순화 위해 raw 호출
    import asyncio

    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    notion.clear_cache()
    return {"status": "archived", "page_id": page_id}
