"""WORKS Drive 임베디드 파일 탐색기 + review-folder + stream + upload/delete.

PR-DD (Phase 4-J 14단계): projects/__init__.py 581 ~ 1013 (~433 lines) 분리.

parent router prefix(`/projects`)는 projects/__init__.py가 그대로 유지.
endpoint 경로 동일.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

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
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user
from app.services import sso_drive
from app.services.mirror_dto import project_from_mirror
from app.settings import get_settings

logger = logging.getLogger("projects.drive")
router = APIRouter()


def _extract_resource_key(drive_url: str) -> str:
    """drive_url의 query string에서 resourceKey 추출 (= NAVER WORKS Drive root fileId)."""
    if not drive_url:
        return ""
    try:
        qs = parse_qs(urlparse(drive_url).query)
    except Exception:  # noqa: BLE001
        return ""
    v = qs.get("resourceKey")
    return v[0] if v else ""


class DriveItemDTO(BaseModel):
    fileId: str
    fileName: str
    fileType: str  # FOLDER | DOC | IMAGE | VIDEO | AUDIO | ZIP | EXE | ETC
    fileSize: int = 0
    modifiedTime: str = ""
    webUrl: str = ""


class DriveChildrenResponse(BaseModel):
    items: list[DriveItemDTO]
    next_cursor: str = ""


class ReviewFolderState(BaseModel):
    """프로젝트의 오늘 날짜 검토자료(0.검토자료/YYYYMMDD) 폴더 상태."""

    ymd: str  # YYYYMMDD
    exists: bool  # day 폴더 존재 여부 (생성하지 않고 조회만)
    folder_url: str = ""
    folder_id: str = ""  # 폴더 fileId — 임베디드 탐색기 직접 진입용
    file_count: int = 0  # FOLDER 제외한 실제 파일 개수


def _today_ymd() -> str:
    return date.today().strftime("%Y%m%d")


async def _review_folder_state(
    page_id: str, db: Session, *, ymd: str
) -> ReviewFolderState:
    """공용 helper — GET/POST 응답 모두 동일 구조."""
    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)
    root_id = _extract_resource_key(project.drive_url)
    if not root_id:
        return ReviewFolderState(ymd=ymd, exists=False)
    found = await sso_drive.find_review_folder(root_id, ymd)
    if not found:
        return ReviewFolderState(ymd=ymd, exists=False)
    day_id, day_url = found
    try:
        body = await sso_drive.list_children(day_id)
        files = body.get("files") or []
        real = [f for f in files if f.get("fileType") != "FOLDER"]
        count = len(real)
    except sso_drive.DriveError as e:
        # PR-BW (silent except 가시화): Drive list 실패 시 count=0 fallback (의도) +
        # 운영 추적용 warning. 폴더 자체는 존재하므로 사용자에 0건으로 보여도 OK.
        logger.warning("review folder list_children 실패 (ymd=%s): %s", ymd, e)
        count = 0
    return ReviewFolderState(
        ymd=ymd,
        exists=True,
        folder_url=day_url,
        folder_id=day_id,
        file_count=count,
    )


@router.get("/{page_id}/review-folder", response_model=ReviewFolderState)
async def get_review_folder(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewFolderState:
    """오늘 날짜의 검토자료 폴더 상태 조회 — 생성하지 않음.

    날인요청 모달에서 [폴더생성]/[폴더열기] 버튼 분기 + 등록 시 경고용.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    return await _review_folder_state(page_id, db, ymd=_today_ymd())


@router.post(
    "/{page_id}/review-folder",
    response_model=ReviewFolderState,
    status_code=status.HTTP_201_CREATED,
)
async def create_review_folder(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewFolderState:
    """[폴더생성] 버튼 — 0.검토자료/오늘날짜 폴더 ensure (idempotent).

    프로젝트 root 폴더가 없으면 502.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)
    root_id = _extract_resource_key(project.drive_url)
    if not root_id:
        raise HTTPException(
            status_code=422,
            detail="프로젝트 Drive 폴더가 아직 생성되지 않았습니다",
        )
    ymd = _today_ymd()
    try:
        await sso_drive.ensure_review_folder(root_id, ymd)
    except sso_drive.DriveError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return await _review_folder_state(page_id, db, ymd=ymd)


@router.get("/{page_id}/drive/children", response_model=DriveChildrenResponse)
async def list_drive_children(
    page_id: str,
    folder_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveChildrenResponse:
    """프로젝트 폴더(또는 그 sub 폴더)의 children list. 임베디드 탐색기용.

    folder_id 미지정 시 프로젝트 root 폴더 (drive_url의 resourceKey).
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")

    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)

    parent_id = folder_id or _extract_resource_key(project.drive_url)
    if not parent_id:
        raise HTTPException(
            status_code=422,
            detail="Drive 폴더가 아직 생성되지 않았습니다 (drive_url 없음)",
        )

    try:
        body: dict[str, Any] = await sso_drive.list_children(parent_id)
    except sso_drive.DriveError as e:
        # 401·token 만료는 sso_drive 내부에서 retry. 그래도 실패면 502.
        raise HTTPException(status_code=502, detail=str(e)) from e

    files = body.get("files") or []
    items: list[DriveItemDTO] = []
    for f in files:
        loc = f.get("resourceLocation")
        items.append(
            DriveItemDTO(
                fileId=str(f.get("fileId") or ""),
                fileName=str(f.get("fileName") or ""),
                fileType=str(f.get("fileType") or "ETC"),
                fileSize=int(f.get("fileSize") or 0),
                modifiedTime=str(f.get("modifiedTime") or ""),
                webUrl=sso_drive.build_file_web_url(
                    str(f.get("fileId") or ""), loc
                ),
            )
        )
    meta = body.get("responseMetaData") or {}
    return DriveChildrenResponse(
        items=items, next_cursor=str(meta.get("nextCursor") or "")
    )


class DriveStreamTokenResponse(BaseModel):
    token: str
    expires_in: int = 300


_STREAM_TOKEN_TTL = 300  # 5분


def _issue_drive_stream_token(
    file_id: str, user_id: int, jwt_secret: str
) -> str:
    """Drive streaming endpoint 인증용 short-lived JWT.

    URL query로 노출되어도 5분 TTL + file_id 고정이라 재사용 위험 적음.
    """
    payload = {
        "fid": file_id,
        "uid": user_id,
        "scope": "drive_stream",
        "exp": int(time.time()) + _STREAM_TOKEN_TTL,
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def _verify_drive_stream_token(token: str, jwt_secret: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise HTTPException(status_code=401, detail="invalid stream token") from e
    if payload.get("scope") != "drive_stream":
        raise HTTPException(status_code=401, detail="wrong scope")
    return payload


@router.get(
    "/{page_id}/drive/issue-token/{file_id}",
    response_model=DriveStreamTokenResponse,
)
def issue_drive_stream_token(
    page_id: str,
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveStreamTokenResponse:
    """Drive 파일 stream용 short-lived JWT 발급."""
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    if db.get(M.MirrorProject, page_id) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    token = _issue_drive_stream_token(file_id, user.id, s.jwt_secret)
    return DriveStreamTokenResponse(token=token, expires_in=_STREAM_TOKEN_TTL)


@router.get("/{page_id}/drive/stream/{file_id}")
async def stream_drive_file(
    page_id: str,
    file_id: str,
    token: str = Query(..., description="issue-token으로 발급한 JWT"),
    file_name: str | None = Query(default=None, alias="name"),
) -> StreamingResponse:
    """short-lived token으로 인증, NAVER WORKS Drive에서 파일 stream을 받아
    그대로 forward. 모든 파일을 attachment로 강제 다운로드.

    httpx의 cross-domain redirect는 default로 Authorization 헤더를 strip하므로
    event_hook으로 매 outbound request에 Bearer 재부착 (apis-storage.worksmobile.com에서
    401 발생 방지).
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    payload = _verify_drive_stream_token(token, s.jwt_secret)
    if payload.get("fid") != file_id:
        raise HTTPException(status_code=401, detail="token/file_id mismatch")

    sd = s.works_drive_sharedrive_id
    if not sd:
        raise HTTPException(status_code=503, detail="WORKS_DRIVE_SHAREDRIVE_ID 미설정")

    bearer = await sso_drive._get_valid_access_token(s)
    upstream_url = (
        f"{s.works_api_base.rstrip('/')}"
        f"/sharedrives/{sd}/files/{file_id}/download"
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
            "drive stream upstream %s: %s", resp.status_code, body[:300]
        )
        raise HTTPException(
            status_code=502, detail=f"upstream {resp.status_code}"
        )

    # 모든 파일을 attachment로 강제 다운로드 (Office protocol/inline 등 분기 폐기).
    # 사용자가 OS 다운로드 폴더에서 더블클릭 → OS 기본 앱(Office/한글/AutoCAD 등) 자동 launch.
    # NOTE: HTTP 헤더는 latin-1만 허용 → 한글 파일명은 RFC 5987 filename*=UTF-8'' 형식으로
    # percent-encoded ASCII로 변환 후 전송. filename(legacy)도 같은 percent-encoded 사용.
    forward_headers: dict[str, str] = {
        "content-type": resp.headers.get("content-type", "application/octet-stream"),
    }
    if "content-length" in resp.headers:
        forward_headers["content-length"] = resp.headers["content-length"]
    safe_name = (file_name or "").replace('"', "").replace("\\", "")
    if safe_name:
        from urllib.parse import quote

        encoded = quote(safe_name, safe="")
        forward_headers["content-disposition"] = (
            f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
        )
    else:
        forward_headers["content-disposition"] = "attachment"

    async def _aclose() -> None:
        await resp.aclose()
        await client.aclose()

    return StreamingResponse(
        resp.aiter_raw(),
        status_code=resp.status_code,
        headers=forward_headers,
        background=BackgroundTask(_aclose),
    )


class DriveUploadResultItem(BaseModel):
    fileName: str
    fileId: str = ""
    fileSize: int = 0
    fileType: str = "ETC"
    webUrl: str = ""
    error: str = ""


class DriveUploadResponse(BaseModel):
    items: list[DriveUploadResultItem]


@router.post(
    "/{page_id}/drive/upload", response_model=DriveUploadResponse
)
async def upload_drive_files(
    page_id: str,
    files: list[UploadFile] = File(...),
    folder_id: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveUploadResponse:
    """드래그&드롭으로 들어온 파일 N개를 NAVER WORKS Drive 폴더에 업로드.

    folder_id가 비면 프로젝트 root 폴더. suffixOnDuplicate=true이므로 이름 충돌 시
    NAVER가 자동 번호 추가. 일부 실패는 result.error로 보고하고 다른 파일은 계속 진행.
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")

    row = db.get(M.MirrorProject, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    project = project_from_mirror(row)

    parent_id = folder_id or _extract_resource_key(project.drive_url)
    if not parent_id:
        raise HTTPException(
            status_code=422, detail="Drive 폴더가 아직 생성되지 않았습니다"
        )

    results: list[DriveUploadResultItem] = []
    for upload in files:
        name = upload.filename or "untitled"
        try:
            content = await upload.read()
            meta = await sso_drive.upload_file(
                parent_id,
                name,
                content,
                content_type=upload.content_type or None,
                settings=s,
            )
            file_id = str(meta.get("fileId") or "")
            results.append(
                DriveUploadResultItem(
                    fileName=str(meta.get("fileName") or name),
                    fileId=file_id,
                    fileSize=int(meta.get("fileSize") or len(content)),
                    fileType=str(meta.get("fileType") or "ETC"),
                    webUrl=sso_drive.build_file_web_url(
                        file_id, meta.get("resourceLocation")
                    ),
                )
            )
        except sso_drive.DriveError as e:
            logger.warning("파일 업로드 실패 %s: %s", name, e)
            results.append(
                DriveUploadResultItem(fileName=name, error=str(e))
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("파일 업로드 중 예외 %s", name)
            results.append(
                DriveUploadResultItem(fileName=name, error=f"내부 오류: {e}")
            )
    return DriveUploadResponse(items=results)


@router.delete(
    "/{page_id}/drive/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_drive_file(
    page_id: str,
    file_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """프로젝트 Drive 안의 파일/폴더를 휴지통으로 이동.

    임베디드 탐색기에서 휴지통 버튼이 호출. 권한은 일반 인증으로 충분
    (날인 검토자가 잘못 올라간 파일 정리 가능).
    """
    s = get_settings()
    if not s.works_drive_enabled:
        raise HTTPException(status_code=503, detail="WORKS Drive 비활성")
    if db.get(M.MirrorProject, page_id) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id 미지정")
    try:
        await sso_drive.delete_file(file_id, settings=s)
    except sso_drive.DriveError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
