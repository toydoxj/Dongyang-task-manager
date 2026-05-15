"""날인요청 승인/반려 endpoint — 1차/2차 승인, 반려.

PR-CI (Phase 4-J 7단계): seal_requests/__init__.py에서 status 전이 3 endpoint 분리.
- PATCH /:id/approve-lead — 1차 승인 (team_lead/admin)
- PATCH /:id/approve-admin — 2차 승인 (admin only)
- PATCH /:id/reject — 반려 (1차는 team_lead/admin, 2차는 admin only)

`_set_status_with_handler` helper + `RejectBody` model도 함께 이동
(이 endpoint들에서만 사용).

다른 helper(`_from_notion_page`, `_sync_linked_task` 등)는 __init__.py에서
lazy import — sub-router include가 파일 끝이라 fully loaded 후 mount.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import require_admin, require_admin_or_lead
from app.services import notion_props as P
from app.services import seal_logic as SL
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync  # PR-CQ: write 즉시 mirror sync

router = APIRouter()

# module-level lazy import — __init__.py 파일 끝의 sub-router include 시점에
# fully loaded라 안전. response_model decorator에 사용해야 해서 module-level 필수.
from app.routers.seal_requests import SealRequestItem  # noqa: E402


class RejectBody(BaseModel):
    reason: str = ""


async def _set_status_with_handler(
    notion: NotionService,
    page_id: str,
    new_status: str,
    handler_field: str,
    handler_date_field: str,
    handler_name: str,
) -> dict[str, Any]:
    today = date.today().isoformat()
    return await notion.update_page(
        page_id,
        {
            "상태": {"select": {"name": new_status}},
            handler_field: {"rich_text": [{"text": {"content": handler_name}}]},
            handler_date_field: {"date": {"start": today}},
        },
    )


@router.patch("/{page_id}/approve-lead", response_model=SealRequestItem)
async def approve_lead(
    page_id: str,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    from app.routers.seal_requests import (
        _bot_send,
        _create_seal_task_bg,
        _find_admins,
        _from_notion_page,
        _resolve_works_id,
        _spawn_task,
        _sync_linked_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur != "1차검토 중":
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태가 '1차검토 중'이 아닙니다 (현재: {cur or '미정'})",
        )
    handler = user.name or user.username
    item = _from_notion_page(page)

    await _set_status_with_handler(
        notion, page_id, "2차검토 중", "팀장처리자", "팀장처리일", handler
    )

    # 1차 검토자 TASK 완료 + 2차 검토자(admin) TASK 생성
    if item.lead_task_id:
        await _sync_linked_task(notion, item.lead_task_id, target="완료")
    project_id_for_task = item.project_ids[0] if item.project_ids else ""
    admins = _find_admins(db)
    admin_reviewer_name = (admins[0].name or "") if admins else ""
    if project_id_for_task and admin_reviewer_name:
        _spawn_task(
            _create_seal_task_bg(
                notion,
                seal_page_id=page_id,
                seal_link_prop="2차검토TASK",
                project_id=project_id_for_task,
                title=f"[날인 2차검토] {item.title}",
                assignee_name=admin_reviewer_name,
                today_iso=date.today().isoformat(),
            )
        )

    # Bot 알림 — admin 전원 (본인 포함)
    msg = (
        f"[2차검토 요청] {item.title}"
        f"\n1차검토자: {handler} / 요청자: {item.requester} / 제출예정일: {item.due_date or '-'}"
    )
    for adm in _find_admins(db):
        _bot_send(_resolve_works_id(adm), msg)

    updated = await notion.get_page(page_id)
    get_sync().upsert_page("seal_requests", updated)  # PR-CQ
    return _from_notion_page(updated)


@router.patch("/{page_id}/approve-admin", response_model=SealRequestItem)
async def approve_admin(
    page_id: str,
    user: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    from app.routers.seal_requests import (
        _bot_send,
        _find_user_by_name,
        _from_notion_page,
        _resolve_works_id,
        _sync_linked_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur not in {"2차검토 중", "1차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"승인 가능 상태가 아님 (현재: {cur or '미정'})",
        )
    handler = user.name or user.username
    item = _from_notion_page(page)

    await _set_status_with_handler(
        notion, page_id, "승인", "관리자처리자", "관리자처리일", handler
    )

    # 2차 검토자 TASK 완료 + (1차 검토자 TASK가 1차 미경유 케이스로 남아있으면 함께 완료)
    # + 요청자 TASK 완료
    if item.admin_task_id:
        await _sync_linked_task(notion, item.admin_task_id, target="완료")
    if item.lead_task_id:
        # 1차 미경유로 admin이 바로 승인한 경우 lead task가 진행 중일 수 있어 같이 완료
        await _sync_linked_task(notion, item.lead_task_id, target="완료")
    if item.linked_task_id:
        await _sync_linked_task(notion, item.linked_task_id, target="완료")

    # Bot 알림 — 요청자에게
    requester_user = _find_user_by_name(db, item.requester)
    msg = (
        f"[승인 완료] {item.title}\n처리자: {handler}"
    )
    _bot_send(_resolve_works_id(requester_user), msg)

    updated = await notion.get_page(page_id)
    get_sync().upsert_page("seal_requests", updated)  # PR-CQ
    return _from_notion_page(updated)


@router.patch("/{page_id}/reject", response_model=SealRequestItem)
async def reject_seal_request(
    page_id: str,
    body: RejectBody,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    from app.routers.seal_requests import (
        _bot_send,
        _find_user_by_name,
        _from_notion_page,
        _resolve_works_id,
        _sync_linked_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur not in {"1차검토 중", "2차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"반려 가능 상태가 아님 (현재: {cur or '미정'})",
        )
    # 정책: 팀장은 1차검토 단계에서만 반려 가능. 2차검토 중인 항목의 반려는 admin only.
    if cur == "2차검토 중" and user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="2차검토 중인 항목의 반려는 관리자만 가능합니다",
        )
    rejector = user.name or user.username
    reason = (body.reason or "").strip()
    update_props: dict[str, Any] = {
        "상태": {"select": {"name": "반려"}},
        "반려사유": {
            "rich_text": [
                {"text": {"content": f"[{rejector}] {reason}" if reason else f"[{rejector}]"}}
            ]
        },
    }
    await notion.update_page(page_id, update_props)

    # 현재 단계 검토자 TASK 완료 (반려도 검토 완료로 간주). 요청자 TASK는
    # 그대로 진행 — 사용자가 재요청하면 다시 1차검토 중으로 돌아감.
    item_for_task = _from_notion_page(page)
    if cur == "1차검토 중" and item_for_task.lead_task_id:
        await _sync_linked_task(notion, item_for_task.lead_task_id, target="완료")
    elif cur == "2차검토 중" and item_for_task.admin_task_id:
        await _sync_linked_task(notion, item_for_task.admin_task_id, target="완료")

    item = _from_notion_page(page)
    requester_user = _find_user_by_name(db, item.requester)
    msg = (
        f"[반려] {item.title}"
        f"\n사유: {reason or '(미기재)'} / 처리자: {rejector}"
    )
    _bot_send(_resolve_works_id(requester_user), msg)

    updated = await notion.get_page(page_id)
    get_sync().upsert_page("seal_requests", updated)  # PR-CQ
    return _from_notion_page(updated)
