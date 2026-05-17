"""계약서 라우터 — PR-FH/1 (계약서 관리 본격 구성).

권한:
- GET: 로그인 사용자 누구나 (열람)
- POST/PATCH/DELETE / file CRUD: require_editor (admin / team_lead / manager)

파일 저장: NAVER WORKS Drive `[계약서]/{프로젝트 CODE}/{원본 filename}`.
- `[계약서]` 폴더 + `{CODE}` 하위 폴더 모두 첫 업로드 시 자동 생성 (`create_folder` idempotent).
- DB row update 실패 시 Drive 파일 즉시 삭제(rollback)로 고아 파일 방지.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
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

logger = logging.getLogger("contracts")

router = APIRouter(prefix="/contracts", tags=["contracts"])

_CONTRACTS_FOLDER_NAME = "[계약서]"
# 파일 형식 allow-list (한국 계약 관행). 확장자(소문자) 기준.
_ALLOWED_EXT = {".pdf", ".doc", ".docx", ".hwp", ".hwpx"}
# Drive upload 최대 사이즈 (30MB).
_MAX_FILE_SIZE = 30 * 1024 * 1024


# ── 헬퍼 ─────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enrich_with_project(
    db: Session, rows: list[Contract]
) -> list[ContractOut]:
    """Contract row에 mirror_projects join으로 project_code/name/client 정보 채워서 응답."""
    if not rows:
        return []
    project_ids = list({r.project_id for r in rows})
    projects = (
        db.query(MirrorProject).filter(MirrorProject.page_id.in_(project_ids)).all()
    )
    project_map = {p.page_id: p for p in projects}
    # client lookup — mirror_projects.client_relation_ids[0] 사용
    client_ids = set()
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
        item = ContractOut.model_validate(r)
        proj = project_map.get(r.project_id)
        if proj is not None:
            item.project_code = proj.code or None
            item.project_name = proj.name or None
            if proj.client_relation_ids:
                cid = proj.client_relation_ids[0]
                item.client_id = cid
                client = client_map.get(cid)
                if client is not None:
                    item.client_name = client.name or None
        out.append(item)
    return out


def _validate_file_ext(file_name: str) -> str:
    """확장자 lower-case 반환 + allow-list 검증."""
    if "." not in file_name:
        raise HTTPException(
            status_code=400, detail="파일 확장자가 없습니다"
        )
    ext = "." + file_name.rsplit(".", 1)[-1].lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않은 파일 형식: {ext} (허용: {sorted(_ALLOWED_EXT)})",
        )
    return ext


async def _resolve_contracts_root_folder() -> str:
    """[계약서] root 폴더 file_id 반환 — 없으면 sharedrive root에 자동 생성."""
    settings = sso_drive.get_settings()
    if not settings.works_drive_root_folder_id:
        raise sso_drive.DriveError("WORKS_DRIVE_ROOT_FOLDER_ID 미설정")
    meta = await sso_drive.create_folder(
        settings, settings.works_drive_root_folder_id, _CONTRACTS_FOLDER_NAME
    )
    return meta.get("file", {}).get("fileId") or meta.get("fileId") or ""


async def _resolve_project_subfolder(project_code: str) -> str:
    """[계약서]/{project_code} 하위 폴더 file_id 반환 — 없으면 생성."""
    settings = sso_drive.get_settings()
    root_id = await _resolve_contracts_root_folder()
    sub_name = (project_code or "_unknown").strip() or "_unknown"
    meta = await sso_drive.create_folder(settings, root_id, sub_name)
    return meta.get("file", {}).get("fileId") or meta.get("fileId") or ""


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
    """발주처 page_id → 프로젝트 page_id 리스트 (mirror_projects.client_relation_ids 매칭)."""
    return [
        p.page_id
        for p in db.query(MirrorProject).all()
        if p.client_relation_ids and client_id in p.client_relation_ids
    ]


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
def create_contract(
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
    return _enrich_with_project(db, [row])[0]


@router.patch("/{contract_id}", response_model=ContractOut)
def update_contract(
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
    # Drive 파일 동반 삭제 — 실패해도 row 삭제는 진행 (warn log)
    if row.drive_file_id:
        try:
            await sso_drive.delete_file(row.drive_file_id)
        except sso_drive.DriveError as e:
            logger.warning("delete_contract: Drive 삭제 실패 %s — %s", row.drive_file_id, e)
    db.delete(row)
    db.commit()


@router.post("/{contract_id}/file", response_model=ContractOut)
async def upload_contract_file(
    contract_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_editor),
    db: Session = Depends(get_db),
) -> ContractOut:
    """multipart 파일 업로드 → Drive 저장 + Contract row 메타 업데이트.

    기존 파일이 있으면 새 파일 업로드 성공 후 옛 Drive 파일 삭제(replace).
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

    project_code = _get_project_code(db, row.project_id)
    try:
        sub_folder_id = await _resolve_project_subfolder(project_code)
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
    new_file_url = upload_result.get("fileUrl") or upload_result.get("webUrl") or ""

    old_file_id = row.drive_file_id
    try:
        row.drive_file_id = new_file_id
        row.drive_url = new_file_url
        row.file_name = raw_name
        row.uploaded_at = _utcnow()
        db.commit()
        db.refresh(row)
    except Exception as e:
        # DB update 실패 — 방금 올린 Drive 파일 삭제(rollback)
        logger.error("upload_contract_file: DB update 실패 — Drive rollback")
        try:
            await sso_drive.delete_file(new_file_id)
        except sso_drive.DriveError as drive_e:
            logger.error("rollback Drive 삭제 실패: %s", drive_e)
        raise HTTPException(status_code=500, detail=f"DB update 실패: {e}")

    # 옛 파일 삭제 — 실패는 warn (replace 성공이 우선)
    if old_file_id and old_file_id != new_file_id:
        try:
            await sso_drive.delete_file(old_file_id)
        except sso_drive.DriveError as e:
            logger.warning("upload_contract_file: 옛 파일 삭제 실패 %s — %s", old_file_id, e)

    # 사용자 created_by 보강 (메타만 만들고 파일 업로드한 사람과 다를 수 있음 — created_by 유지)
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
