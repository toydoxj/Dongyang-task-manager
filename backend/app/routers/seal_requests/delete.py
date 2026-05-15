"""날인요청 취소(archive) endpoint.

PR-CU (Phase 4-J 10단계): seal_requests/__init__.py에서 DELETE 분리.
- DELETE /:id — 작성자 본인 또는 admin. 구조검토서는 마지막 번호만 archive,
  중간 번호는 [날인취소] prefix + 상태 '취소' 마킹.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import get_current_user
from app.services import file_storage as storage
from app.services import notion_props as P
from app.services import seal_logic as SL
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.seal_requests.delete")
router = APIRouter()


def _db_id() -> str:
    """meta.py와 동일 helper — 중복 정의 (외과적, 2줄)."""
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(status_code=500, detail="NOTION_DB_SEAL_REQUESTS 미설정")
    return db_id


@router.delete("/{page_id}")
async def delete_seal_request(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """취소 — 작성자 본인 또는 admin.

    구조검토서이며 문서번호가 발급되어 있으면:
        - 후속 번호가 이미 있음(중간 번호)  → archive 안 함, 제목 [날인취소] prefix + 상태 '반려'
        - 후속 번호 없음(마지막 번호)        → archive (다음 발급에서 그 번호 회수)
    그 외 유형: archive.
    """
    from app.routers.seal_requests import (
        _can_access,
        _from_notion_page,
        _get_title_prop_name,
        _parse_attachments_meta,
        _sync_linked_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    if not (is_owner or user.role == "admin"):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자는 모두 가능)"
        )

    seal_type = SL.normalize_type(P.select_name(props, "날인유형"))
    doc_no = P.rich_text(props, "문서번호").strip()
    keep_with_marker = False
    if seal_type == "구조검토서" and doc_no:
        try:
            is_last = await SL.is_last_review_doc_number(
                notion, _db_id(), doc_no=doc_no
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("마지막 번호 검사 실패: %s — 보수적으로 흔적 남김", e)
            is_last = False
        keep_with_marker = not is_last

    item = _from_notion_page(page)

    if keep_with_marker:
        # 흔적 남김: 제목 prefix + 상태 '취소' (재요청 차단) + 첨부메타 비움
        cur_title = ""
        for v in props.values():
            if isinstance(v, dict) and v.get("type") == "title":
                arr = v.get("title") or []
                cur_title = arr[0].get("plain_text", "") if arr else ""
                break
        new_title = (
            cur_title if cur_title.startswith("[날인취소] ") else f"[날인취소] {cur_title}"
        )
        title_prop = await _get_title_prop_name(notion)
        await notion.update_page(
            page_id,
            {
                title_prop: {"title": [{"text": {"content": new_title}}]},
                "상태": {"select": {"name": "취소"}},
                "반려사유": {
                    "rich_text": [
                        {"text": {"content": f"[취소 by {user.name or user.username}]"}}
                    ]
                },
                "첨부메타": {"rich_text": [{"text": {"content": "[]"}}]},
            },
        )
    else:
        # legacy S3 cleanup (있으면)
        for a in _parse_attachments_meta(props):
            if a.storage_key:
                try:
                    storage.delete_object(key=a.storage_key)
                except storage.StorageError as e:
                    logger.warning("S3 cleanup 실패 (%s): %s", a.storage_key, e)
        await asyncio.to_thread(
            notion._client.pages.update, page_id=page_id, archived=True
        )

    # 연결 task 완료 처리 (요청자 + 검토자 모두) — 취소도 라이프사이클 종료로 간주.
    for tid in (item.linked_task_id, item.lead_task_id, item.admin_task_id):
        if tid:
            await _sync_linked_task(notion, tid, target="완료")

    # PR-CQ: mirror 즉시 sync (취소 마킹은 upsert, archive는 archive_page).
    if keep_with_marker:
        try:
            updated = await notion.get_page(page_id)
            get_sync().upsert_page("seal_requests", updated)
        except Exception as e:  # noqa: BLE001
            logger.warning("delete mirror upsert 실패 (page=%s): %s", page_id, e)
    else:
        get_sync().archive_page("seal_requests", page_id)

    notion.clear_cache()
    return {
        "status": "marked-cancelled" if keep_with_marker else "archived",
    }
