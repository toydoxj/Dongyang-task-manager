"""날인요청 첨부파일 endpoint — download/preview (read) + add (write).

PR-CH (Phase 4-J 6단계): read-only 2 endpoint(GET download/preview).
PR-CT (Phase 4-J 9단계): write endpoint(POST attachments) 추가 — 같은 파일에서
첨부 흐름 일원화.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import get_current_user
from app.services import file_storage as storage
from app.services import notion_props as P
from app.services import seal_logic as SL
from app.services import sso_drive
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.seal_requests.attachments")
router = APIRouter()

# module-level lazy import — sub-router include가 파일 끝(__init__.py fully loaded 후).
from app.routers.seal_requests import SealRequestItem  # noqa: E402


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


# ── 첨부 add (보완 업로드) ──


@router.post("/{page_id}/attachments", response_model=SealRequestItem)
async def add_attachments(
    page_id: str,
    files: list[UploadFile] = File(..., description="추가 첨부파일 (다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """반려된 요청을 보완해 파일을 추가하면서 상태를 '1차검토 중'으로 되돌림.

    권한: 작성자 본인 또는 admin/team_lead.
    상태: '반려' 또는 '1차검토 중'(legacy '요청') 일 때만.

    PR-CT (Phase 4-J 9단계): __init__.py에서 attachments.py로 이동.
    """
    from app.routers.seal_requests import (
        _attachments_to_meta_json,
        _can_access,
        _failed_to_partial,
        _from_notion_page,
        _max_bytes,
        _parse_attachments_meta,
        _project_summary_from_db,
    )

    if not files:
        raise HTTPException(status_code=400, detail="추가할 파일을 선택하세요")
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    props = page.get("properties", {})
    cur_status = SL.normalize_status(P.select_name(props, "상태"))
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    is_lead_admin = user.role in {"admin", "team_lead"}
    if not (is_owner or is_lead_admin):
        raise HTTPException(
            status_code=403, detail="본인 요청만 보완 업로드 가능"
        )
    if cur_status not in {"반려", "1차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"'{cur_status}' 상태에서는 재업로드 불가 (반려 또는 1차검토 중에서만)",
        )

    # 프로젝트 root 폴더 → 일자 폴더
    project_ids = P.relation_ids(props, "프로젝트")
    project_id = project_ids[0] if project_ids else ""
    _code, _name, _drive_url, root_folder_id = _project_summary_from_db(
        db, project_id
    )
    s_set = get_settings()
    today = date.today()
    today_iso = today.isoformat()
    ymd = today.strftime("%Y%m%d")

    existing_meta = _parse_attachments_meta(props)
    new_meta = [
        {
            "drive_file_id": a.drive_file_id,
            "key": a.storage_key,
            "name": a.name,
            "size": a.size,
            "type": a.content_type,
        }
        for a in existing_meta
        if (a.drive_file_id or a.storage_key)
    ]

    max_bytes = _max_bytes()
    failed: list[str] = []
    folder_url = ""
    if not s_set.works_drive_enabled or not root_folder_id:
        failed.extend(
            [f"{(f.filename or 'file.bin')}: Drive 미연결" for f in files]
        )
    else:
        try:
            day_folder_id, day_folder_url = await sso_drive.ensure_review_folder(
                root_folder_id, ymd
            )
            folder_url = day_folder_url
        except sso_drive.DriveError as exc:
            day_folder_id = ""
            failed.extend(
                [f"{(f.filename or 'file.bin')}: 폴더 생성 실패 ({exc})" for f in files]
            )
        if day_folder_id:
            for f in files:
                data = await f.read()
                fname = f.filename or "file.bin"
                if len(data) > max_bytes:
                    failed.append(
                        f"{fname}: 한도 {max_bytes // (1024 * 1024)}MB 초과"
                    )
                    continue
                try:
                    meta = await sso_drive.upload_file(
                        day_folder_id,
                        fname,
                        data,
                        content_type=f.content_type or "application/octet-stream",
                    )
                    new_meta.append(
                        {
                            "drive_file_id": meta.get("fileId", ""),
                            "name": meta.get("fileName") or fname,
                            "size": int(meta.get("fileSize") or len(data)),
                            "type": f.content_type or "application/octet-stream",
                        }
                    )
                except sso_drive.DriveError as exc:
                    failed.append(f"{fname}: {exc}")

    update_props: dict[str, Any] = {
        "첨부메타": {
            "rich_text": [
                {"text": {"content": _attachments_to_meta_json(new_meta)}}
            ]
        },
        "상태": {"select": {"name": "1차검토 중"}},
    }
    if folder_url:
        update_props["첨부폴더URL"] = {"url": folder_url}
    if cur_status == "반려":
        existing_note = P.rich_text(props, "비고")
        actor = user.name or user.username
        new_note = (
            f"{existing_note}\n[재제출 by {actor} {today_iso}] 파일 {len(files)}개 보완"
            if existing_note
            else f"[재제출 by {actor} {today_iso}] 파일 {len(files)}개 보완"
        )
        update_props["비고"] = {"rich_text": [{"text": {"content": new_note}}]}
        update_props["팀장처리자"] = {"rich_text": [{"text": {"content": ""}}]}
        update_props["팀장처리일"] = {"date": None}

    # PR-CA: notion update 최종 실패 시 partial_errors로 노출.
    try:
        await notion.update_page(page_id, update_props)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "seal_request 첨부 add 노션 update 실패 — Drive 파일은 존재 (page=%s)",
            page_id,
        )
        failed.append(f"노션 첨부메타 업데이트 실패: {exc}")
    if failed:
        logger.warning("첨부 추가 일부 실패 (page=%s): %s", page_id, failed)
    final = await notion.get_page(page_id)
    # PR-CQ: mirror 즉시 sync.
    get_sync().upsert_page("seal_requests", final)
    item = _from_notion_page(final)
    item.partial_errors = [_failed_to_partial(msg) for msg in failed]
    return item
