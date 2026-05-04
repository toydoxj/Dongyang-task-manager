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
from app.services.project_stage_sync import reconcile_projects_for_task
from app.services.sync import get_sync
from app.settings import get_settings

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _ensure_can_modify_task(user: User, assignees: list[str] | None) -> None:
    """일반직원은 본인 담당 task만 수정/삭제 가능. admin/team_lead 는 패스.

    mirror에 row가 없는 미연결 task(이미 archive됨 등)는 통과시켜 노션 호출
    단계에서 적절한 에러가 발생하도록 한다 (조용한 403 회피).
    """
    if user.role in {"admin", "team_lead"}:
        return
    if assignees is None:
        return
    if not user.name or user.name not in assignees:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인 담당 task만 수정/삭제할 수 있습니다",
        )


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
        # — .any() 는 'value = ANY(array)' 로 GIN 미적용. .contains() 가 @> 컴파일 → GIN 활용.
        stmt = stmt.where(M.MirrorTask.project_ids.contains([project_id]))  # type: ignore[attr-defined]
    if assignee:
        stmt = stmt.where(M.MirrorTask.assignees.contains([assignee]))  # type: ignore[attr-defined]
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
    # 프로젝트 진행단계 자동 동기화 — 새 task가 이번주 활성이면 '진행중'으로 promote
    background.add_task(reconcile_projects_for_task, notion, task.project_ids)
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Task:
    # 변경 전 mirror 읽기 — 권한 체크 + project_ids 보존 + 기간 partial update 보강 용도.
    prev_row = db.get(M.MirrorTask, page_id)
    _ensure_can_modify_task(
        user, list(prev_row.assignees) if prev_row else None
    )
    prev_project_ids = list(prev_row.project_ids or []) if prev_row else []

    # 노션 date prop은 start 필수, end도 명시 안 보내면 기존 값 클리어됨.
    # 한쪽만 변경(non-empty)되고 다른 쪽이 None(=미지정) 인 경우에만 mirror
    # 현재 값으로 보강해 의도치 않은 클리어 / 'date.start required' 502 회피.
    # body.*_date == "" 는 'clear' 신호이므로 절대 보강하지 않는다.
    if prev_row is not None:
        new_end = (
            body.end_date is not None and body.end_date != ""
        )
        new_start = (
            body.start_date is not None and body.start_date != ""
        )
        if (
            new_end
            and body.start_date is None
            and prev_row.start_date is not None
        ):
            body = body.model_copy(
                update={"start_date": prev_row.start_date.isoformat()}
            )
        elif (
            new_start
            and body.end_date is None
            and prev_row.end_date is not None
        ):
            body = body.model_copy(
                update={"end_date": prev_row.end_date.isoformat()}
            )

    props = task_update_to_props(body)
    if not props:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="갱신할 필드가 없습니다"
        )

    page = await notion.update_page(page_id, props)
    get_sync().upsert_page("tasks", page)  # write-through
    task = Task.from_notion_page(page)
    background.add_task(task_calendar_sync.sync_task, task)
    # 프로젝트 진행단계 자동 동기화 — 이전+신규 project_ids union
    affected = list({*prev_project_ids, *task.project_ids})
    background.add_task(reconcile_projects_for_task, notion, affected)
    return task


@router.delete("/{page_id}")
async def archive_task(
    page_id: str,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """노션은 영구 삭제 대신 archive 사용."""
    prev_row = db.get(M.MirrorTask, page_id)
    _ensure_can_modify_task(
        user, list(prev_row.assignees) if prev_row else None
    )
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    notion.clear_cache()
    get_sync().archive_page("tasks", page_id)
    background.add_task(task_calendar_sync.unsync_task, page_id)
    return {"status": "archived", "page_id": page_id}
