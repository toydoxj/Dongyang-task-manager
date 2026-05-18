"""계약서 라우터 — PR-FH/1 (도메인 신설) + PR-FI/1 (프로젝트 연동).

권한:
- GET: 로그인 사용자 누구나 (열람)
- POST/PATCH/DELETE / file CRUD: require_editor (admin / team_lead / manager)

파일 저장 (PR-FI/1): 프로젝트별 자체 폴더의 "6. 계약서" sub-folder에 PDF 저장.
경로: `[CODE]프로젝트명/6. 계약서/{원본 filename}` (sso_drive.SUB_FOLDERS 표준).
- 프로젝트 root + 7개 sub-folder는 ensure_project_folder가 idempotent 보장.
- DB row update 실패 시 Drive 파일 즉시 삭제(rollback)로 고아 파일 방지.

Contract ↔ Project 동기화 (PR-FI/1):
- Contract create/update/delete 후 해당 project의 모든 contracts를 aggregate.
- `contract_signed=True` (한 번이라도 signed_date 있으면, 삭제 후에도 True 유지).
- `contract_start = min(non-null start_date)`, `contract_end = max(non-null end_date)`.
- mirror_projects + 노션 양쪽 update (Codex 협의: 동기 호출 + 부분 성공 허용).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.contract import (
    Contract,
    ContractCreate,
    ContractListResponse,
    ContractOut,
    ContractUpdate,
)
from app.models.mirror import MirrorClient, MirrorProject
from app.security import get_current_user, require_editor
from app.services import sso_drive
from app.services.notion import get_notion
from app.services.sync import get_sync

logger = logging.getLogger("contracts")

router = APIRouter(prefix="/contracts", tags=["contracts"])

_CONTRACTS_SUB_FOLDER = "6. 계약서"
# 파일 형식 allow-list (한국 계약 관행). 확장자(소문자) 기준.
_ALLOWED_EXT = {".pdf", ".doc", ".docx", ".hwp", ".hwpx"}
# Drive upload 최대 사이즈 (30MB).
_MAX_FILE_SIZE = 30 * 1024 * 1024


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backfill_drive_url(row: Contract) -> None:
    """PR-GC: 옛 row의 drive_url이 비어있고 drive_file_id가 있으면 URL 조립.

    이전 코드는 upload 시 drive_url을 빈 문자열로 저장하는 버그가 있었음.
    응답 직전에 in-memory로 조립 (DB UPDATE는 안 함 — 다음 upload나 별도 backfill에 위임).
    """
    if not row.drive_url and row.drive_file_id:
        row.drive_url = sso_drive.build_file_web_url(row.drive_file_id, None)


def _enrich_with_project(
    db: Session, rows: list[Contract]
) -> list[ContractOut]:
    """Contract row에 mirror_projects join + client_id 우선순위 적용.

    PR-FI/4: contract.client_id가 있으면 그것이 우선, 없으면 project.client_relation_ids[0] fallback.
    """
    if not rows:
        return []
    project_ids = list({r.project_id for r in rows})
    projects = (
        db.query(MirrorProject).filter(MirrorProject.page_id.in_(project_ids)).all()
    )
    project_map = {p.page_id: p for p in projects}
    # 발주처 lookup 대상 = contract.client_id 또는 project.client_relation_ids[0]
    client_ids: set[str] = set()
    for r in rows:
        if r.client_id:
            client_ids.add(r.client_id)
    for p in projects:
        if p.client_relation_ids:
            client_ids.add(p.client_relation_ids[0])
    clients = (
        db.query(MirrorClient).filter(MirrorClient.page_id.in_(client_ids)).all()
        if client_ids
        else []
    )
    client_map = {c.page_id: c for c in clients}

    out: list[ContractOut] = []
    for r in rows:
        # PR-GC: 옛 row(drive_url 빈 문자열) backfill — in-memory만, DB 변경 없음.
        _backfill_drive_url(r)
        item = ContractOut.model_validate(r)
        proj = project_map.get(r.project_id)
        if proj is not None:
            item.project_code = proj.code or None
            item.project_name = proj.name or None
        # PR-FI/4: contract.client_id 우선, 없으면 project 발주처 fallback.
        effective_cid: str | None = None
        if r.client_id:
            effective_cid = r.client_id
        elif proj is not None and proj.client_relation_ids:
            effective_cid = proj.client_relation_ids[0]
        if effective_cid:
            item.client_id = effective_cid
            client = client_map.get(effective_cid)
            if client is not None:
                item.client_name = client.name or None
        out.append(item)
    return out


def _validate_file_ext(file_name: str) -> str:
    if "." not in file_name:
        raise HTTPException(status_code=400, detail="파일 확장자가 없습니다")
    ext = "." + file_name.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 파일 형식: {ext} (허용: {sorted(_ALLOWED_EXT)})",
        )
    return ext


async def _resolve_project_contract_folder(
    db: Session, project_id: str
) -> str:
    """프로젝트별 자체 폴더의 "6. 계약서" sub-folder file_id 반환 (PR-FI/1).

    `ensure_project_folder + find_child_folder` 조합으로 idempotent 보장.
    누락 시 self-heal (재생성).
    """
    proj = db.get(MirrorProject, project_id)
    if proj is None:
        raise sso_drive.DriveError(f"프로젝트 {project_id} 를 찾을 수 없음")
    if not proj.code or not proj.name:
        raise sso_drive.DriveError(
            f"프로젝트 {project_id} 의 code/name 비어있음 (Drive 폴더 생성 불가)"
        )
    return await sso_drive.find_or_create_project_subfolder(
        proj.code, proj.name, _CONTRACTS_SUB_FOLDER
    )


def _get_project_code(db: Session, project_id: str) -> str:
    proj = db.get(MirrorProject, project_id)
    return (proj.code if proj else "") or ""


def _ensure_project_exists(db: Session, project_id: str) -> None:
    """프로젝트 존재 검증 (mirror_projects). 부재 시 400.

    test (SQLite)에서는 mirror_* 테이블이 없어 항상 None이라 monkeypatch로 우회한다.
    """
    if db.get(MirrorProject, project_id) is None:
        raise HTTPException(
            status_code=400, detail="존재하지 않는 프로젝트입니다"
        )


def _list_project_ids_by_client(db: Session, client_id: str) -> list[str]:
    return [
        p.page_id
        for p in db.query(MirrorProject).all()
        if p.client_relation_ids and client_id in p.client_relation_ids
    ]


def _aggregate_project_contract_state(
    db: Session, project_id: str
) -> tuple[bool, date | None, date | None]:
    """프로젝트의 모든 contracts를 aggregate.

    반환: (has_any_signed, min_start, max_end). null 날짜는 무시 (Codex 협의).
    """
    contracts = (
        db.query(Contract).filter(Contract.project_id == project_id).all()
    )
    has_signed = any(c.signed_date is not None for c in contracts)
    starts = [c.start_date for c in contracts if c.start_date is not None]
    ends = [c.end_date for c in contracts if c.end_date is not None]
    return (
        has_signed,
        min(starts) if starts else None,
        max(ends) if ends else None,
    )


async def _sync_project_contract_fields(
    db: Session, project_id: str
) -> None:
    """Contract CUD 후 mirror_projects + 노션 Project 페이지의 계약 필드 sync.

    - `Project.contract_signed = True` (한 번이라도 signed_date 있으면, True 유지 정책)
    - `Project.contract_start = min(start_date)`, `Project.contract_end = max(end_date)`
    - 노션 컬럼명: "계약" (checkbox) / "계약기간" (date range).

    실패는 silent log (부분 성공 — Contract 저장은 이미 commit, Codex 협의).
    PR-GF: notion service를 함수 내부에서 lazy 얻음. Depends(get_notion)으로 받으면
    NOTION_API_KEY 없는 환경(CI/test)에서 endpoint 진입 자체가 502로 차단됨.
    """
    try:
        has_signed, start, end = _aggregate_project_contract_state(
            db, project_id
        )
        proj = db.get(MirrorProject, project_id)
        if proj is None:
            return  # 프로젝트 자체가 없으면 skip

        # 현재 contract_signed 상태 확인 (True 유지 정책)
        current_signed = bool(
            (proj.properties or {}).get("계약", {}).get("checkbox", False)
        )
        new_signed = current_signed or has_signed

        props: dict[str, Any] = {}
        if new_signed and not current_signed:
            props["계약"] = {"checkbox": True}

        # 기간 sync — start/end 둘 다 없으면 update skip (Project 기존 값 유지).
        if start or end:
            props["계약기간"] = {
                "date": {
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                }
            }

        if not props:
            return

        # PR-GF: 노션 service lazy 획득 (NOTION_API_KEY 없으면 NotionApiError → 아래 except로).
        notion = get_notion()
        page = await notion.update_page(project_id, props)
        get_sync().upsert_page("projects", page)
        logger.info(
            "contract sync: project=%s signed=%s start=%s end=%s",
            project_id,
            new_signed,
            start,
            end,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "contract sync 실패 (project=%s): %s — 부분 성공 (Contract row는 저장됨)",
            project_id,
            e,
        )


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("", response_model=ContractListResponse)
def list_contracts(
    project_id: str | None = Query(None, description="프로젝트 page_id"),
    client_id: str | None = Query(None, description="발주처 page_id (project join)"),
    q: str | None = Query(None, description="title / file_name 검색"),
    year: int | None = Query(None, description="signed_date 연도"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractListResponse:
    qry = db.query(Contract)
    if project_id:
        qry = qry.filter(Contract.project_id == project_id)
    if client_id:
        proj_ids = _list_project_ids_by_client(db, client_id)
        if not proj_ids:
            return ContractListResponse(items=[], count=0)
        qry = qry.filter(Contract.project_id.in_(proj_ids))
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(Contract.title.ilike(like), Contract.file_name.ilike(like)))
    if year is not None:
        from sqlalchemy import extract

        qry = qry.filter(extract("year", Contract.signed_date) == year)

    total = qry.count()
    rows = (
        qry.order_by(
            Contract.signed_date.desc().nullslast(), Contract.id.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = _enrich_with_project(db, rows)
    return ContractListResponse(items=items, count=total)


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContractOut:
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")
    return _enrich_with_project(db, [row])[0]


@router.post(
    "", response_model=ContractOut, status_code=status.HTTP_201_CREATED
)
async def create_contract(
    body: ContractCreate,
    user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractOut:
    _ensure_project_exists(db, body.project_id)
    if (
        body.end_date is not None
        and body.start_date is not None
        and body.end_date < body.start_date
    ):
        raise HTTPException(
            status_code=400, detail="end_date는 start_date 이상이어야 합니다"
        )
    row = Contract(
        project_id=body.project_id,
        client_id=body.client_id,
        title=body.title,
        signed_date=body.signed_date,
        start_date=body.start_date,
        end_date=body.end_date,
        amount=body.amount,
        vat_included=body.vat_included,
        note=body.note,
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await _sync_project_contract_fields(db,body.project_id)
    return _enrich_with_project(db, [row])[0]


@router.patch("/{contract_id}", response_model=ContractOut)
async def update_contract(
    contract_id: int,
    body: ContractUpdate,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractOut:
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")
    if body.title is not None:
        row.title = body.title
    # PR-FI/4: client_id는 명시적 null도 허용 (계약서별 발주처 해제). 빈 문자열도 null로 처리.
    if "client_id" in body.model_fields_set:
        row.client_id = body.client_id or None
    if body.signed_date is not None:
        row.signed_date = body.signed_date
    if body.start_date is not None:
        row.start_date = body.start_date
    if body.end_date is not None:
        row.end_date = body.end_date
    if body.amount is not None:
        row.amount = body.amount
    if body.vat_included is not None:
        row.vat_included = body.vat_included
    if body.note is not None:
        row.note = body.note
    if (
        row.end_date is not None
        and row.start_date is not None
        and row.end_date < row.start_date
    ):
        raise HTTPException(
            status_code=400, detail="end_date는 start_date 이상이어야 합니다"
        )
    db.commit()
    db.refresh(row)
    await _sync_project_contract_fields(db,row.project_id)
    return _enrich_with_project(db, [row])[0]


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: int,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")
    project_id = row.project_id
    # Drive 파일 동반 삭제 — 실패해도 row 삭제는 진행 (warn log)
    if row.drive_file_id:
        try:
            await sso_drive.delete_file(row.drive_file_id)
        except sso_drive.DriveError as e:
            logger.warning("delete_contract: Drive 삭제 실패 %s — %s", row.drive_file_id, e)
    db.delete(row)
    db.commit()
    # 삭제 후에도 contract_signed=True 유지 (사용자 정책). 기간은 남은 contracts 기준 재계산.
    await _sync_project_contract_fields(db,project_id)


@router.get("/{contract_id}/file/download")
async def download_contract_file(
    contract_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """PR-GG: backend가 NAVER WORKS Drive에서 파일을 stream forward.

    이전 PR-GE는 signed URL을 frontend에 전달했으나 NAVER 응답 URL이
    `auth=OPEN` 패턴이라 외부 redirect 시 401 "Authentication failed" 발생.
    projects/drive.py의 stream_drive_file 패턴 동일 적용 — backend가 Bearer로
    NAVER 다운로드 → raw bytes를 attachment로 forward. NAVER 측 인증 우회.

    httpx의 cross-domain redirect는 default로 Authorization 헤더를 strip하므로
    event_hook으로 매 outbound request에 Bearer 재부착 (apis-storage 도메인에서
    401 발생 방지).
    """
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")
    if not row.drive_file_id:
        raise HTTPException(status_code=404, detail="첨부된 파일이 없습니다")

    s = sso_drive.get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    sd = s.works_drive_sharedrive_id
    if not sd:
        raise HTTPException(status_code=503, detail="WORKS_DRIVE_SHAREDRIVE_ID 미설정")

    bearer = await sso_drive._get_valid_access_token(s)
    upstream_url = (
        f"{s.works_api_base.rstrip('/')}"
        f"/sharedrives/{sd}/files/{row.drive_file_id}/download"
    )

    async def _attach_bearer(request: httpx.Request) -> None:
        request.headers["Authorization"] = f"Bearer {bearer}"

    client = httpx.AsyncClient(
        timeout=600.0,
        follow_redirects=True,
        event_hooks={"request": [_attach_bearer]},
    )
    try:
        resp = await client.send(
            client.build_request("GET", upstream_url),
            stream=True,
        )
    except Exception:
        await client.aclose()
        raise

    if resp.status_code >= 400:
        body = await resp.aread()
        await client.aclose()
        logger.warning(
            "contract download upstream %s: %s", resp.status_code, body[:300]
        )
        raise HTTPException(
            status_code=502, detail=f"upstream {resp.status_code}"
        )

    forward_headers: dict[str, str] = {
        "content-type": resp.headers.get("content-type", "application/octet-stream"),
    }
    if "content-length" in resp.headers:
        forward_headers["content-length"] = resp.headers["content-length"]
    safe_name = (row.file_name or f"contract_{contract_id}").replace('"', "").replace("\\", "")
    from urllib.parse import quote

    encoded = quote(safe_name, safe="")
    forward_headers["content-disposition"] = (
        f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
    )

    async def _aclose() -> None:
        await resp.aclose()
        await client.aclose()

    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers=forward_headers,
        background=BackgroundTask(_aclose),
    )


@router.post("/{contract_id}/file", response_model=ContractOut)
async def upload_contract_file(
    contract_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractOut:
    """multipart 파일 업로드 → 프로젝트별 "6. 계약서" 폴더에 저장 + 메타 update.

    기존 파일 있으면 새 파일 업로드 성공 후 옛 Drive 파일 삭제(replace).
    Drive 업로드 성공 후 DB update 실패 시 새 파일 즉시 삭제(rollback).
    """
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")

    raw_name = file.filename or ""
    if not raw_name:
        raise HTTPException(status_code=400, detail="파일명이 비어 있습니다")
    _validate_file_ext(raw_name)

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기 한도 초과 ({_MAX_FILE_SIZE // 1024 // 1024}MB)",
        )

    try:
        sub_folder_id = await _resolve_project_contract_folder(db, row.project_id)
        upload_result = await sso_drive.upload_file(
            sub_folder_id,
            raw_name,
            content,
            content_type=file.content_type,
        )
    except sso_drive.DriveError as e:
        raise HTTPException(status_code=500, detail=f"WORKS Drive 업로드 실패: {e}")

    new_file_id = (
        upload_result.get("fileId")
        or upload_result.get("file", {}).get("fileId")
        or ""
    )
    # PR-GC fix: NAVER WORKS Drive 응답엔 fileUrl/webUrl 키가 없음 — share URL 패턴
    # 으로 직접 조립 (sso_drive.build_file_web_url). 이전엔 빈 문자열로 저장되어
    # frontend가 falsy 처리 → 「첨부 없음」 표시되는 회귀.
    new_file_url = (
        upload_result.get("fileUrl")
        or upload_result.get("webUrl")
        or sso_drive.build_file_web_url(new_file_id, upload_result.get("resourceLocation"))
    )

    old_file_id = row.drive_file_id
    try:
        row.drive_file_id = new_file_id
        row.drive_url = new_file_url
        row.file_name = raw_name
        row.uploaded_at = _utcnow()
        db.commit()
        db.refresh(row)
    except Exception as e:
        logger.error("upload_contract_file: DB update 실패 — Drive rollback")
        try:
            await sso_drive.delete_file(new_file_id)
        except sso_drive.DriveError as drive_e:
            logger.error("rollback Drive 삭제 실패: %s", drive_e)
        raise HTTPException(status_code=500, detail=f"DB update 실패: {e}")

    if old_file_id and old_file_id != new_file_id:
        try:
            await sso_drive.delete_file(old_file_id)
        except sso_drive.DriveError as e:
            logger.warning("upload_contract_file: 옛 파일 삭제 실패 %s — %s", old_file_id, e)

    _ = user
    return _enrich_with_project(db, [row])[0]


@router.delete("/{contract_id}/file", response_model=ContractOut)
async def delete_contract_file(
    contract_id: int,
    _user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractOut:
    row = db.get(Contract, contract_id)
    if row is None:
        raise HTTPException(status_code=404, detail="계약서를 찾을 수 없습니다")
    if not row.drive_file_id:
        return _enrich_with_project(db, [row])[0]
    try:
        await sso_drive.delete_file(row.drive_file_id)
    except sso_drive.DriveError as e:
        logger.warning("delete_contract_file: Drive 삭제 실패 — %s", e)
    row.drive_file_id = None
    row.drive_url = None
    row.file_name = None
    row.uploaded_at = None
    db.commit()
    db.refresh(row)
    return _enrich_with_project(db, [row])[0]
