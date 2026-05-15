"""날인요청 첨부파일 read endpoint — download URL, preview stream proxy.

PR-CH (Phase 4-J 6단계): seal_requests/__init__.py에서 read-only 첨부 endpoint 분리.
- GET /{page_id}/download/{idx} — fresh signed URL 발급
- GET /{page_id}/preview/{idx} — stream proxy + Content-Disposition: inline

write(POST /:id/attachments)는 큰 함수 + Drive 업로드 + 노션 update라 별도 cycle.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import get_current_user
from app.services import file_storage as storage
from app.services import notion_props as P
from app.services import sso_drive
from app.services.notion import NotionService, get_notion

router = APIRouter()


def _get_attachment_or_404(page: dict[str, Any], idx: int):
    """첨부메타 + 노션 files fallback에서 idx 번째 항목 반환. 없으면 404.

    PR-CH: 원본 __init__.py:1252 helper를 그대로 이동.
    SealAttachment / _parse_attachments_meta는 __init__.py에 잔여 — lazy import.
    """
    from app.routers.seal_requests import SealAttachment, _parse_attachments_meta

    props = page.get("properties", {})
    items = _parse_attachments_meta(props)
    if not items:
        items = [
            SealAttachment(name=f["name"], legacy_url=f["url"])
            for f in P.files(props, "첨부파일")
        ]
    if idx < 0 or idx >= len(items):
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다")
    return items[idx]


@router.get("/{page_id}/download/{idx}")
async def get_attachment_url(
    page_id: str,
    idx: int,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    # _can_access는 __init__.py의 module-level helper. include가 파일 끝에서
    # 일어나므로 __init__.py fully loaded 상태에서 lazy import OK.
    from app.routers.seal_requests import _can_access

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)
    # 우선순위: drive_file_id → storage_key → legacy_url
    if item.drive_file_id:
        try:
            url = await sso_drive.get_download_url(item.drive_file_id)
        except sso_drive.DriveError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"url": url, "name": item.name}
    if item.storage_key:
        try:
            url = storage.presigned_get_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"url": url, "name": item.name}
    return {"url": item.legacy_url, "name": item.name}


@router.get("/{page_id}/preview/{idx}")
async def preview_attachment(
    page_id: str,
    idx: int,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """stream proxy + Content-Disposition: inline."""
    from app.routers.seal_requests import _can_access

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)

    if item.drive_file_id:
        try:
            url = await sso_drive.get_download_url(item.drive_file_id)
        except sso_drive.DriveError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    elif item.storage_key:
        try:
            url = storage.presigned_inline_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        url = item.legacy_url
    filename = item.name or "file.bin"

    client = httpx.AsyncClient(timeout=120.0)
    try:
        upstream = await client.send(
            client.build_request("GET", url), stream=True
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502, detail=f"파일 fetch 실패: {exc}"
        ) from exc
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=upstream.status_code, detail="파일 fetch 실패"
        )

    media_type = upstream.headers.get(
        "content-type", item.content_type or "application/octet-stream"
    )

    async def _iter():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )
