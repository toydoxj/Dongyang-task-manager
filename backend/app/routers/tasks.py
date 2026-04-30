"""/api/tasks — 통합 업무TASK CRUD. read는 mirror, write는 노션 + write-through."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
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
from app.services import task_calendar_sync
from app.services.mirror_dto import task_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    project_id: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    status_name: str | None = Query(default=None, alias="status"),
    mine: bool = Query(default=False),
    schedule_only: bool = Query(
        default=False,
        description="True면 일정 task만 (분류=외근/출장/휴가 OR 활동=외근/출장)",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    if mine:
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    stmt = select(M.MirrorTask).where(M.MirrorTask.archived.is_(False))
    if project_id:
        # Postgres ARRAY contains: project_ids @> ARRAY[project_id]
        stmt = stmt.where(M.MirrorTask.project_ids.any(project_id))  # type: ignore[attr-defined]
    if assignee:
        stmt = stmt.where(M.MirrorTask.assignees.any(assignee))  # type: ignore[attr-defined]
    if status_name:
        stmt = stmt.where(M.MirrorTask.status == status_name)
    if schedule_only:
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(
                M.MirrorTask.category.in_(
                    ["외근", "출장", "휴가", "휴가(연차)"]
                ),
                M.MirrorTask.activity.in_(["외근", "출장"]),
            )
        )
    stmt = stmt.order_by(M.MirrorTask.end_date.asc().nullslast())
    rows = db.execute(stmt).scalars().all()
    items = [task_from_mirror(r) for r in rows]
    return TaskListResponse(items=items, count=len(items))


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreateRequest,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Task:
    # 종료예정일 미지정 시 시작일과 동일하게 (단순 일정 task UX 개선)
    if body.start_date and not body.end_date:
        body.end_date = body.start_date
    db_id = get_settings().notion_db_tasks
    props = task_create_to_props(body)
    page = await notion.create_page(db_id, props)
    get_sync().upsert_page("tasks", page)  # write-through
    task = Task.from_notion_page(page)
    # WORKS Calendar 단방향 동기화 (best-effort, 실패해도 응답 영향 없음)
    background.add_task(task_calendar_sync.sync_task, task)
    return task


@router.get("/{page_id}", response_model=Task)
async def get_task(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Task:
    row = db.get(M.MirrorTask, page_id)
    if row is not None and not row.archived:
        return task_from_mirror(row)
    # mirror 미존재 → 노션 fallback + upsert
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("tasks", page)
    return Task.from_notion_page(page)


@router.patch("/{page_id}", response_model=Task)
async def update_task(
    page_id: str,
    body: TaskUpdateRequest,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Task:
    props = task_update_to_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="갱신할 필드가 없습니다"
        )
    page = await notion.update_page(page_id, props)
    get_sync().upsert_page("tasks", page)  # write-through
    task = Task.from_notion_page(page)
    background.add_task(task_calendar_sync.sync_task, task)
    return task


@router.delete("/{page_id}")
async def archive_task(
    page_id: str,
    background: BackgroundTasks,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """노션은 영구 삭제 대신 archive 사용."""
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    notion.clear_cache()
    get_sync().archive_page("tasks", page_id)
    background.add_task(task_calendar_sync.unsync_task, page_id)
    return {"status": "archived", "page_id": page_id}
