"""날인요청 라우터 — 노션 DB 직접 read/write + 첨부파일 + 2단계 승인.

흐름:
    [요청] 사용자 작성 (상태=요청)
       ↓
    [1차] 팀장/관리자 승인 (상태=팀장승인)
       ↓
    [최종] 관리자 승인 (상태=완료)
       ↘ 반려 (사유 비고 append)
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user, require_admin, require_admin_or_lead
from app.services import file_storage as storage
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

router = APIRouter(prefix="/seal-requests", tags=["seal-requests"])

_VALID_TYPES = {"구조계산서", "도면", "검토서", "기타"}
_VALID_STATUSES = {"요청", "팀장승인", "관리자승인", "완료", "반려"}


def _max_bytes() -> int:
    return get_settings().storage_max_file_mb * 1024 * 1024


class SealAttachment(BaseModel):
    name: str
    # idx 기반 안정적 ID (정렬 후 0..N-1). frontend가 download/preview 호출 시 사용.
    storage_key: str = ""  # S3 key (S3에 저장된 경우)
    size: int = 0
    content_type: str = ""
    # 호환: 기존 노션 files property
    legacy_url: str = ""


class SealRequestItem(BaseModel):
    id: str
    title: str = ""
    project_ids: list[str] = []
    seal_type: str = ""
    status: str = "요청"
    requester: str = ""
    lead_handler: str = ""
    admin_handler: str = ""
    requested_at: str | None = None
    lead_handled_at: str | None = None
    admin_handled_at: str | None = None
    due_date: str | None = None
    note: str = ""
    attachments: list[SealAttachment] = []
    created_time: str | None = None
    last_edited_time: str | None = None


class SealListResponse(BaseModel):
    items: list[SealRequestItem]
    count: int


class PendingCount(BaseModel):
    count: int


class RejectBody(BaseModel):
    reason: str = ""


def _parse_attachments_meta(props: dict[str, Any]) -> list[SealAttachment]:
    """첨부메타 rich_text 컬럼의 JSON 파싱. 파싱 실패/빈 값이면 빈 리스트."""
    raw = P.rich_text(props, "첨부메타")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        out: list[SealAttachment] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            out.append(
                SealAttachment(
                    name=str(it.get("name", "")),
                    storage_key=str(it.get("key", "")),
                    size=int(it.get("size", 0) or 0),
                    content_type=str(it.get("type", "")),
                )
            )
        return out
    except (ValueError, TypeError):
        return []


def _from_notion_page(page: dict[str, Any]) -> SealRequestItem:
    props = page.get("properties", {})
    s, _ = P.date_range(props, "요청일")
    lead_s, _ = P.date_range(props, "팀장처리일")
    admin_s, _ = P.date_range(props, "관리자처리일")
    due_s, _ = P.date_range(props, "제출예정일")

    # S3 메타 우선, 없으면 노션 files (legacy) fallback
    attachments = _parse_attachments_meta(props)
    if not attachments:
        attachments = [
            SealAttachment(name=f["name"], legacy_url=f["url"])
            for f in P.files(props, "첨부파일")
        ]

    return SealRequestItem(
        id=page.get("id", ""),
        title=P.title(props, "제목"),
        project_ids=P.relation_ids(props, "프로젝트"),
        seal_type=P.select_name(props, "날인유형"),
        status=P.select_name(props, "상태") or "요청",
        requester=P.rich_text(props, "요청자"),
        lead_handler=P.rich_text(props, "팀장처리자"),
        admin_handler=P.rich_text(props, "관리자처리자"),
        requested_at=s,
        lead_handled_at=lead_s,
        admin_handled_at=admin_s,
        due_date=due_s,
        note=P.rich_text(props, "비고"),
        attachments=attachments,
        created_time=page.get("created_time"),
        last_edited_time=page.get("last_edited_time"),
    )


def _db_id() -> str:
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_SEAL_REQUESTS 미설정",
        )
    return db_id


def _can_access(user: User, page: dict[str, Any], db: Session) -> bool:
    """날인요청 페이지 접근 가능 여부.

    허용 조건 (OR):
    - admin / team_lead
    - 본인이 요청자
    - 요청에 연결된 프로젝트의 담당자 또는 담당팀 소속
    """
    if user.role in {"admin", "team_lead"}:
        return True
    me = user.name or ""
    if not me:
        return False
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자")
    if me == requester:
        return True
    project_ids = P.relation_ids(props, "프로젝트")
    if not project_ids:
        return False
    rows = db.execute(
        select(M.MirrorProject.assignees, M.MirrorProject.teams).where(
            M.MirrorProject.page_id.in_(project_ids)
        )
    ).all()
    for assignees, teams in rows:
        if me in (assignees or []):
            return True
    return False


def _filter_accessible(
    user: User, pages: list[dict[str, Any]], db: Session
) -> list[dict[str, Any]]:
    if user.role in {"admin", "team_lead"}:
        return pages
    me = user.name or ""
    if not me:
        return []
    # 한 번에 모든 프로젝트 fetch (N+1 방지)
    all_project_ids: set[str] = set()
    for p in pages:
        for pid in P.relation_ids(p.get("properties", {}), "프로젝트"):
            all_project_ids.add(pid)
    project_assignees: dict[str, list[str]] = {}
    if all_project_ids:
        rows = db.execute(
            select(
                M.MirrorProject.page_id, M.MirrorProject.assignees
            ).where(M.MirrorProject.page_id.in_(all_project_ids))
        ).all()
        project_assignees = {pid: (assigns or []) for pid, assigns in rows}

    out: list[dict[str, Any]] = []
    for p in pages:
        props = p.get("properties", {})
        if me == P.rich_text(props, "요청자"):
            out.append(p)
            continue
        for pid in P.relation_ids(props, "프로젝트"):
            if me in project_assignees.get(pid, []):
                out.append(p)
                break
    return out


@router.get("", response_model=SealListResponse)
async def list_seal_requests(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealListResponse:
    pages = await notion.query_all(
        _db_id(),
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    if project_id:
        pages = [
            p
            for p in pages
            if project_id
            in P.relation_ids(p.get("properties", {}), "프로젝트")
        ]
    pages = _filter_accessible(user, pages, db)
    items = [_from_notion_page(p) for p in pages]
    return SealListResponse(items=items, count=len(items))


@router.get("/pending-count", response_model=PendingCount)
async def get_pending_count(
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> PendingCount:
    """본인이 처리해야 할 건수 (사이드바 알림 배지용).

    - team_lead: 상태='요청' 인 건수 (1차 처리 대기)
    - admin: 상태='팀장승인' 인 건수 (2차 처리 대기)
    - 그 외: 0
    """
    target_status: str | None = None
    if user.role == "team_lead":
        target_status = "요청"
    elif user.role == "admin":
        target_status = "팀장승인"
    if target_status is None:
        return PendingCount(count=0)
    pages = await notion.query_all(
        _db_id(),
        filter={
            "property": "상태",
            "select": {"equals": target_status},
        },
    )
    return PendingCount(count=len(pages))


@router.post("", response_model=SealRequestItem, status_code=status.HTTP_201_CREATED)
async def create_seal_request(
    project_id: str = Form(..., description="노션 프로젝트 page_id"),
    seal_type: str = Form(..., description="구조계산서/도면/검토서/기타"),
    title: str = Form("", description="제목 (생략 시 'YYYY-MM-DD 요청자 - 유형')"),
    due_date: str = Form("", description="제출 예정일 (YYYY-MM-DD, 선택)"),
    note: str = Form(""),
    files: list[UploadFile] = File(..., description="첨부 파일 (최소 1개, 다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> SealRequestItem:
    if seal_type not in _VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"잘못된 날인유형: {seal_type}")
    if not files:
        raise HTTPException(status_code=400, detail="첨부파일 1개 이상 필요")

    requester = user.name or user.username
    today = date.today().isoformat()
    auto_title = title.strip() or f"{today} {requester} - {seal_type}"
    max_bytes = _max_bytes()

    # 1) 노션 페이지 먼저 생성 (page_id 확보 — S3 prefix에 사용)
    init_props: dict[str, Any] = {
        "제목": {"title": [{"text": {"content": auto_title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "날인유형": {"select": {"name": seal_type}},
        "상태": {"select": {"name": "요청"}},
        "요청자": {"rich_text": [{"text": {"content": requester}}]},
        "요청일": {"date": {"start": today}},
        "비고": {"rich_text": [{"text": {"content": note}}]},
    }
    if due_date.strip():
        init_props["제출예정일"] = {"date": {"start": due_date}}
    page = await notion.create_page(_db_id(), init_props)
    page_id = page["id"]

    # 2) 파일들을 S3에 업로드 (실패 시 페이지는 그대로 유지 — 비고에 기록)
    attachments_meta: list[dict[str, Any]] = []
    failed: list[str] = []
    for f in files:
        data = await f.read()
        fname = f.filename or "file.bin"
        if len(data) > max_bytes:
            failed.append(f"{fname}: 한도 {max_bytes // (1024 * 1024)}MB 초과")
            continue
        try:
            key = storage.build_key(f"seal-requests/{page_id}", fname)
            storage.put_object(
                key=key,
                data=data,
                content_type=f.content_type or "application/octet-stream",
            )
            attachments_meta.append(
                {
                    "key": key,
                    "name": fname,
                    "size": len(data),
                    "type": f.content_type or "application/octet-stream",
                }
            )
        except storage.StorageError as exc:
            failed.append(f"{fname}: {exc}")

    # 3) 첨부메타 + 실패 기록을 노션 page에 update
    update_props: dict[str, Any] = {
        "첨부메타": {
            "rich_text": [
                {"text": {"content": json.dumps(attachments_meta, ensure_ascii=False)}}
            ]
        },
    }
    if failed:
        fail_note = (
            f"\n[업로드 실패]\n" + "\n".join(f" - {x}" for x in failed)
        )
        update_props["비고"] = {
            "rich_text": [{"text": {"content": note + fail_note}}]
        }
    updated = await notion.update_page(page_id, update_props)
    return _from_notion_page(updated)


async def _set_status_with_handler(
    notion: NotionService,
    page_id: str,
    new_status: str,
    handler_field: str,
    handler_date_field: str,
    handler_name: str,
) -> dict[str, Any]:
    """상태 변경 + 처리자/처리일 기록 헬퍼."""
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
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = P.select_name(page.get("properties", {}), "상태")
    if cur != "요청":
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태가 '요청'이 아닙니다 (현재: {cur or '미정'})",
        )
    updated = await _set_status_with_handler(
        notion,
        page_id,
        "팀장승인",
        "팀장처리자",
        "팀장처리일",
        user.name or user.username,
    )
    return _from_notion_page(updated)


@router.patch("/{page_id}/approve-admin", response_model=SealRequestItem)
async def approve_admin(
    page_id: str,
    user: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = P.select_name(page.get("properties", {}), "상태")
    if cur not in {"팀장승인", "관리자승인"}:
        raise HTTPException(
            status_code=400,
            detail=f"팀장 1차 승인 후에만 가능 (현재: {cur or '미정'})",
        )
    updated = await _set_status_with_handler(
        notion,
        page_id,
        "완료",
        "관리자처리자",
        "관리자처리일",
        user.name or user.username,
    )
    return _from_notion_page(updated)


@router.patch("/{page_id}/reject", response_model=SealRequestItem)
async def reject_seal_request(
    page_id: str,
    body: RejectBody,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    existing_note = P.rich_text(page.get("properties", {}), "비고")
    rejector = user.name or user.username
    new_note = (
        f"{existing_note}\n[반려 by {rejector}] {body.reason}"
        if existing_note
        else f"[반려 by {rejector}] {body.reason}"
    )
    updated = await notion.update_page(
        page_id,
        {
            "상태": {"select": {"name": "반려"}},
            "비고": {"rich_text": [{"text": {"content": new_note}}]},
        },
    )
    return _from_notion_page(updated)


def _get_attachment_or_404(
    page: dict[str, Any], idx: int
) -> SealAttachment:
    props = page.get("properties", {})
    items = _parse_attachments_meta(props)
    if not items:
        # legacy: 노션 files property fallback
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
    """다운로드용 URL — S3 presigned 또는 노션 legacy URL."""
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)
    if item.storage_key:
        try:
            url = storage.presigned_get_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"url": url, "name": item.name}
    # legacy
    return {"url": item.legacy_url, "name": item.name}


@router.get("/{page_id}/preview/{idx}")
async def preview_attachment(
    page_id: str,
    idx: int,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """첨부파일을 backend가 stream proxy + Content-Disposition: inline.

    노션 signed URL은 'attachment' 헤더라 새 탭 열어도 다운로드됨.
    여기서 inline으로 변환하면 PDF/이미지가 브라우저에서 바로 미리보기.
    frontend는 authFetch → blob → URL.createObjectURL 패턴으로 호출.
    """
    import httpx
    from fastapi.responses import StreamingResponse

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)

    # S3 첨부: presigned inline URL 발급 후 stream proxy
    if item.storage_key:
        try:
            url = storage.presigned_inline_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        # legacy: 노션 file URL
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


@router.post("/{page_id}/attachments", response_model=SealRequestItem)
async def add_attachments(
    page_id: str,
    files: list[UploadFile] = File(..., description="추가 첨부파일 (다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    """반려된 요청을 보완해 파일을 추가하면서 상태를 '요청'으로 되돌림.

    권한: 작성자 본인 또는 admin/team_lead.
    상태: '반려' 또는 '요청' 일 때만 (이미 승인 완료된 건은 변경 안 함).
    """
    if not files:
        raise HTTPException(status_code=400, detail="추가할 파일을 선택하세요")
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    props = page.get("properties", {})
    cur_status = P.select_name(props, "상태")
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    is_lead_admin = user.role in {"admin", "team_lead"}
    if not (is_owner or is_lead_admin):
        raise HTTPException(
            status_code=403, detail="본인 요청만 보완 업로드 가능"
        )
    if cur_status not in {"반려", "요청"}:
        raise HTTPException(
            status_code=400,
            detail=f"'{cur_status}' 상태에서는 재업로드 불가 (반려 또는 요청 상태에서만)",
        )

    # 새 파일 S3 업로드 + 기존 메타에 추가
    existing_meta = _parse_attachments_meta(props)
    new_meta = [
        {
            "key": a.storage_key,
            "name": a.name,
            "size": a.size,
            "type": a.content_type,
        }
        for a in existing_meta
        if a.storage_key
    ]
    max_bytes = _max_bytes()
    failed: list[str] = []
    for f in files:
        data = await f.read()
        fname = f.filename or "file.bin"
        if len(data) > max_bytes:
            failed.append(f"{fname}: 한도 {max_bytes // (1024 * 1024)}MB 초과")
            continue
        try:
            key = storage.build_key(f"seal-requests/{page_id}", fname)
            storage.put_object(
                key=key,
                data=data,
                content_type=f.content_type or "application/octet-stream",
            )
            new_meta.append(
                {
                    "key": key,
                    "name": fname,
                    "size": len(data),
                    "type": f.content_type or "application/octet-stream",
                }
            )
        except storage.StorageError as exc:
            failed.append(f"{fname}: {exc}")

    today = date.today().isoformat()
    update_props: dict[str, Any] = {
        "첨부메타": {
            "rich_text": [
                {"text": {"content": json.dumps(new_meta, ensure_ascii=False)}}
            ]
        },
        # 반려 → 요청으로 되돌림 (재처리 시작). 비고에 기록 append.
        "상태": {"select": {"name": "요청"}},
    }
    # 반려 상태였으면 비고에 재제출 기록 추가
    if cur_status == "반려":
        existing_note = P.rich_text(props, "비고")
        actor = user.name or user.username
        new_note = (
            f"{existing_note}\n[재제출 by {actor} {today}] 파일 {len(files)}개 보완"
            if existing_note
            else f"[재제출 by {actor} {today}] 파일 {len(files)}개 보완"
        )
        update_props["비고"] = {"rich_text": [{"text": {"content": new_note}}]}
        # 처리자/처리일 reset (새로 1차 검토부터)
        update_props["팀장처리자"] = {"rich_text": [{"text": {"content": ""}}]}
        update_props["팀장처리일"] = {"date": None}

    updated = await notion.update_page(page_id, update_props)
    return _from_notion_page(updated)


@router.delete("/{page_id}")
async def delete_seal_request(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """archive — 작성자 본인 또는 admin."""
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    requester = P.rich_text(page.get("properties", {}), "요청자")
    is_owner = (user.name or user.username) == requester
    if not (is_owner or user.role == "admin"):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자는 모두 가능)"
        )
    # S3 cleanup (존재하는 경우)
    for a in _parse_attachments_meta(page.get("properties", {})):
        if a.storage_key:
            storage.delete_object(key=a.storage_key)
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    notion.clear_cache()
    return {"status": "archived"}
