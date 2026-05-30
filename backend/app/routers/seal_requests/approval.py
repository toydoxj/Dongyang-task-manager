"""날인요청 승인/반려 endpoint — 1차/2차 승인, 반려.

PR-CI (Phase 4-J 7단계): seal_requests/__init__.py에서 status 전이 3 endpoint 분리.
- PATCH /:id/approve-lead — 1차 승인 (team_lead/admin)
- PATCH /:id/approve-admin — 2차 승인 (admin only)
- PATCH /:id/reject — 반려 (1차는 team_lead/admin, 2차는 admin only)

PR-FP Phase 1.3.2: 노션 호출 제거 → mirror direct update + outbox enqueue.
사용자 응답 ~50ms (이전 1~2초). drain worker가 노션 push.

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
from app.models import mirror as M
from app.models.auth import User
from app.models.notion_outbox import OP_UPDATE
from app.security import require_admin, require_admin_or_lead
from app.services.notion import NotionService, get_notion
from app.services.notion_outbox import enqueue
from app.services.seal_request_mirror import apply_update_to_mirror

router = APIRouter()

# module-level lazy import — __init__.py 파일 끝의 sub-router include 시점에
# fully loaded라 안전. response_model decorator에 사용해야 해서 module-level 필수.
from app.routers.seal_requests import SealRequestItem  # noqa: E402


class RejectBody(BaseModel):
    reason: str = ""


def _status_change_props(
    new_status: str,
    handler_field: str,
    handler_date_field: str,
    handler_name: str,
) -> dict[str, Any]:
    """status 전이 update_props 빌더 (mirror + outbox 공통 payload)."""
    today = date.today().isoformat()
    return {
        "상태": {"select": {"name": new_status}},
        handler_field: {"rich_text": [{"text": {"content": handler_name}}]},
        handler_date_field: {"date": {"start": today}},
    }


def _fetch_mirror_or_404(db: Session, page_id: str) -> M.MirrorSealRequest:
    """mirror row 가져오기. 없으면 404 (sync lag 또는 잘못된 page_id)."""
    row = db.get(M.MirrorSealRequest, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="날인요청을 찾을 수 없습니다")
    return row


def _row_to_item(row: M.MirrorSealRequest) -> SealRequestItem:
    """mirror row → SealRequestItem (PR-FL helper 재사용)."""
    from app.routers.seal_requests import _from_notion_page
    from app.routers.seal_requests.list_endpoint import _mirror_row_to_notion_page

    return _from_notion_page(_mirror_row_to_notion_page(row))


@router.patch("/{page_id}/approve-lead", response_model=SealRequestItem)
async def approve_lead(
    page_id: str,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """1차 승인 — mirror direct update + outbox enqueue (PR-FP). 사용자 응답 즉시."""
    from app.routers.seal_requests import (
        _bot_send,
        _create_seal_task_bg,
        _find_admins,
        _resolve_works_id,
        _spawn_task,
        _sync_seal_tasks_bg,
    )

    row = _fetch_mirror_or_404(db, page_id)
    if row.status != "1차검토 중":
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태가 '1차검토 중'이 아닙니다 (현재: {row.status or '미정'})",
        )
    handler = user.name or user.username
    item_before = _row_to_item(row)  # 사전 lead_task_id 캡처 (post-update 시 동일)

    update_props = _status_change_props(
        "2차검토 중", "팀장처리자", "팀장처리일", handler
    )
    apply_update_to_mirror(row, update_props)
    enqueue(
        db, aggregate_type="seal_requests", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()  # mirror + outbox 원자성

    # ── 이하 fire-and-forget (사용자 응답 path 외) ──
    # 1차 검토자 TASK 완료 + 2차 검토자(admin) TASK 생성 (tasks 도메인 — PR-FP+1로 분리)
    _spawn_task(
        _sync_seal_tasks_bg(
            notion,
            page_id,
            lead_task_id=item_before.lead_task_id,
            include_lead=True,
        )
    )
    project_id_for_task = item_before.project_ids[0] if item_before.project_ids else ""
    admins = _find_admins(db)
    admin_reviewer_name = (admins[0].name or "") if admins else ""
    if project_id_for_task and admin_reviewer_name:
        _spawn_task(
            _create_seal_task_bg(
                notion,
                seal_page_id=page_id,
                seal_link_prop="2차검토TASK",
                project_id=project_id_for_task,
                title=f"[날인 2차검토] {item_before.title}",
                assignee_name=admin_reviewer_name,
                today_iso=date.today().isoformat(),
            )
        )

    # Bot 알림 — admin 전원 (본인 포함)
    msg = (
        f"[2차검토 요청] {item_before.title}"
        f"\n1차검토자: {handler} / 요청자: {item_before.requester} / 제출예정일: {item_before.due_date or '-'}"
    )
    for adm in _find_admins(db):
        _bot_send(_resolve_works_id(adm), msg)

    return _row_to_item(row)


@router.patch("/{page_id}/approve-admin", response_model=SealRequestItem)
async def approve_admin(
    page_id: str,
    user: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """2차 승인 — mirror direct update + outbox enqueue (PR-FP). 사용자 응답 즉시."""
    from app.routers.seal_requests import (
        _bot_send,
        _find_user_by_name,
        _resolve_works_id,
        _spawn_task,
        _sync_seal_tasks_bg,
    )

    row = _fetch_mirror_or_404(db, page_id)
    if row.status not in {"2차검토 중", "1차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"승인 가능 상태가 아님 (현재: {row.status or '미정'})",
        )
    handler = user.name or user.username
    item_before = _row_to_item(row)

    update_props = _status_change_props(
        "승인", "관리자처리자", "관리자처리일", handler
    )
    apply_update_to_mirror(row, update_props)
    enqueue(
        db, aggregate_type="seal_requests", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()

    # ── fire-and-forget (사용자 응답 path 외) ──
    # 2차 + 1차(미경유 케이스) + 요청자 TASK 완료
    _spawn_task(
        _sync_seal_tasks_bg(
            notion,
            page_id,
            linked_task_id=item_before.linked_task_id,
            lead_task_id=item_before.lead_task_id,
            admin_task_id=item_before.admin_task_id,
            include_linked=True,
            include_lead=True,
            include_admin=True,
        )
    )

    # Bot 알림 — 요청자에게
    requester_user = _find_user_by_name(db, item_before.requester)
    msg = f"[승인 완료] {item_before.title}\n처리자: {handler}"
    _bot_send(_resolve_works_id(requester_user), msg)

    return _row_to_item(row)


@router.patch("/{page_id}/reject", response_model=SealRequestItem)
async def reject_seal_request(
    page_id: str,
    body: RejectBody,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """반려 — mirror direct update + outbox enqueue (PR-FP). 사용자 응답 즉시."""
    from app.routers.seal_requests import (
        _bot_send,
        _find_user_by_name,
        _resolve_works_id,
        _spawn_task,
        _sync_seal_tasks_bg,
    )

    row = _fetch_mirror_or_404(db, page_id)
    cur = row.status
    if cur not in {"1차검토 중", "2차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"반려 가능 상태가 아님 (현재: {cur or '미정'})",
        )
    if cur == "2차검토 중" and user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="2차검토 중인 항목의 반려는 관리자만 가능합니다",
        )
    rejector = user.name or user.username
    reason = (body.reason or "").strip()
    item_before = _row_to_item(row)

    update_props: dict[str, Any] = {
        "상태": {"select": {"name": "반려"}},
        "반려사유": {
            "rich_text": [
                {"text": {"content": f"[{rejector}] {reason}" if reason else f"[{rejector}]"}}
            ]
        },
    }
    apply_update_to_mirror(row, update_props)
    enqueue(
        db, aggregate_type="seal_requests", aggregate_id=page_id,
        op=OP_UPDATE, payload=update_props, notion_page_id=page_id,
    )
    db.commit()

    # ── fire-and-forget ──
    _spawn_task(
        _sync_seal_tasks_bg(
            notion,
            page_id,
            lead_task_id=item_before.lead_task_id,
            admin_task_id=item_before.admin_task_id,
            include_lead=cur == "1차검토 중",
            include_admin=cur == "2차검토 중",
        )
    )

    requester_user = _find_user_by_name(db, item_before.requester)
    msg = (
        f"[반려] {item_before.title}"
        f"\n사유: {reason or '(미기재)'} / 처리자: {rejector}"
    )
    _bot_send(_resolve_works_id(requester_user), msg)

    return _row_to_item(row)
