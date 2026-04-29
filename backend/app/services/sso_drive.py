"""NAVER WORKS Drive — 프로젝트별 폴더 자동 생성 (Phase 2, user-token 방식).

NAVER WORKS Drive API는 user account 토큰만 받음 (Service Account JWT 미지원).
admin이 1회 file scope 동의 → access_token + refresh_token을 drive_credentials에 보관 →
모든 자동 폴더 생성에 재사용 + 만료 시 refresh_token으로 자동 갱신.

흐름:
1. /api/admin/drive/connect → admin이 NAVER WORKS authorize URL 동의
2. /api/admin/drive/callback → access_token + refresh_token 저장
3. ensure_project_folder → DB의 access_token 사용 (만료 60초 전부터 refresh)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.drive_creds import DriveCredential
from app.settings import Settings, get_settings

logger = logging.getLogger("sso.drive")

_TOKEN_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/token"
_HTTP_TIMEOUT = 15.0
# 프로젝트 폴더 하위 7개 sub 폴더 — 회사 표준 (Q7 고정)
SUB_FOLDERS: tuple[str, ...] = (
    "1. 건축도면",
    "2. 구조도면",
    "3. 구조계산서",
    "4. 구조해석및설계",
    "5. 문서(심의자료 등)",
    "6. 계약서",
    "7. 기타",
)


class DriveError(Exception):
    """Drive 흐름 중 사용자에게 노출 가능한 에러."""


# ── DB credential helper ──


def _load_creds(db: Session) -> DriveCredential | None:
    return db.get(DriveCredential, 1)


def save_creds(
    db: Session,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int,
    scope: str,
    granted_by_user_id: int | None,
    granted_by_email: str,
) -> DriveCredential:
    """admin 동의 콜백 후 토큰 저장. 항상 id=1 single row upsert."""
    expires_at = datetime.now(UTC) + timedelta(seconds=max(60, int(expires_in)))
    row = db.get(DriveCredential, 1)
    if row is None:
        row = DriveCredential(id=1)
        db.add(row)
    row.access_token = access_token
    row.refresh_token = refresh_token or row.refresh_token  # 비어있으면 보존
    row.expires_at = expires_at
    row.scope = scope or ""
    row.granted_by_user_id = granted_by_user_id
    row.granted_by_email = granted_by_email
    row.updated_at = datetime.now(UTC)
    return row


# ── Token refresh ──
# Drive 위임 토큰의 발급은 SSO 흐름(/auth/works/login?drive=1)이 담당.
# 본 모듈은 DB에 저장된 토큰을 만료 시 refresh + Drive API 호출만 담당.


async def _refresh(settings: Settings, refresh_token: str) -> dict[str, Any]:
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.works_client_id,
        "client_secret": settings.works_client_secret,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                _TOKEN_ENDPOINT,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            raise DriveError(f"refresh 네트워크 오류: {e}") from e
        if resp.status_code != 200:
            logger.warning(
                "drive refresh 실패: %s %s", resp.status_code, resp.text
            )
            raise DriveError(
                f"토큰 갱신 실패 ({resp.status_code}) — admin이 다시 연결해야 합니다"
            )
        return resp.json()


# ── access_token 사용/갱신 (전역 lock) ──

_token_lock = asyncio.Lock()


async def _get_valid_access_token(settings: Settings) -> str:
    """DB의 access_token이 만료 60초 전이면 refresh. 단일 lock으로 중복 refresh 방지."""
    async with _token_lock:
        db = SessionLocal()
        try:
            row = _load_creds(db)
            if row is None or not row.access_token:
                raise DriveError(
                    "Drive 자격 미설정 — admin이 /api/admin/drive/connect 로 연결 필요"
                )
            now = datetime.now(UTC)
            if row.expires_at is None:
                expires_at = now
            else:
                ea = row.expires_at
                expires_at = ea if ea.tzinfo else ea.replace(tzinfo=UTC)
            if expires_at - now > timedelta(seconds=60):
                return row.access_token
            if not row.refresh_token:
                raise DriveError(
                    "access_token 만료 + refresh_token 없음 — admin 재연결 필요"
                )
            body = await _refresh(settings, row.refresh_token)
            new_access = body.get("access_token", "")
            new_refresh = body.get("refresh_token", row.refresh_token)
            expires_in = int(body.get("expires_in", 3600))
            scope = str(body.get("scope", row.scope))
            row.access_token = new_access
            row.refresh_token = new_refresh
            row.expires_at = now + timedelta(seconds=max(60, expires_in))
            row.scope = scope
            row.updated_at = now
            db.commit()
            return new_access
        finally:
            db.close()


# ── Drive HTTP helper ──


async def _api(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{settings.works_api_base.rstrip('/')}{path}"
    token = await _get_valid_access_token(settings)

    async def _call(t: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            return await client.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {t}"},
            )

    resp = await _call(token)
    if resp.status_code == 401:
        # 만료/회수 가능성 — refresh 강제 후 재시도
        async with _token_lock:
            db = SessionLocal()
            try:
                row = _load_creds(db)
                if row and row.refresh_token:
                    body = await _refresh(settings, row.refresh_token)
                    row.access_token = body.get("access_token", row.access_token)
                    row.refresh_token = body.get(
                        "refresh_token", row.refresh_token
                    )
                    expires_in = int(body.get("expires_in", 3600))
                    row.expires_at = datetime.now(UTC) + timedelta(
                        seconds=max(60, expires_in)
                    )
                    row.updated_at = datetime.now(UTC)
                    db.commit()
                    token = row.access_token
            finally:
                db.close()
        resp = await _call(token)
    if resp.status_code >= 400:
        logger.warning(
            "Drive API 오류 %s %s: %s %s",
            method,
            path,
            resp.status_code,
            resp.text,
        )
        raise DriveError(f"Drive API 오류 ({resp.status_code}) {path}")
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


# ── 폴더 생성·조회 ──


async def find_child_folder(
    settings: Settings, parent_id: str, name: str
) -> dict[str, Any] | None:
    """parent 아래에서 같은 이름 폴더가 있으면 metadata 반환.

    NAVER WORKS Drive API:
      - sharedrive root list: GET /sharedrives/{sd}/files
      - 특정 folder children: GET /sharedrives/{sd}/files?parentFolderId={parent}
        (parent는 별도 fileId(base64url) 또는 sharedrive_id)
    """
    sd = settings.works_drive_sharedrive_id
    if not sd:
        raise DriveError("WORKS_DRIVE_SHAREDRIVE_ID 미설정")
    params: dict[str, Any] = {}
    if parent_id and parent_id != sd:
        params["parentFolderId"] = parent_id
    body = await _api(
        settings, "GET", f"/sharedrives/{sd}/files", params=params
    )
    items = (
        body.get("files")
        or body.get("items")
        or body.get("children")
        or body.get("list")
        or []
    )
    for it in items:
        item_name = it.get("fileName") or it.get("name") or ""
        # NAVER WORKS spec: 폴더는 fileType=FOLDER. file/ETC/IMAGE 등은 skip
        # (잘못 만들어진 0byte 파일을 폴더로 매칭하지 않도록)
        if item_name == name and it.get("fileType") == "FOLDER":
            return it
    return None


async def create_folder(
    settings: Settings, parent_id: str, name: str
) -> dict[str, Any]:
    """parent 아래 폴더 생성. 이미 있으면 메타 반환 (idempotent).

    NAVER WORKS Drive API 공식 spec:
      - root에 생성:  POST /sharedrives/{sd}/files/createfolder
      - 폴더 내부:    POST /sharedrives/{sd}/files/{parent_fileId}/createfolder
      body: {"fileName": "..."}
      → 201 응답에 fileId/parentFileId/fileType="FOLDER" 즉시 포함
    """
    existing = await find_child_folder(settings, parent_id, name)
    if existing is not None:
        return existing
    sd = settings.works_drive_sharedrive_id
    if parent_id and parent_id != sd:
        path = f"/sharedrives/{sd}/files/{parent_id}/createfolder"
    else:
        path = f"/sharedrives/{sd}/files/createfolder"
    body = await _api(settings, "POST", path, json={"fileName": name})
    if not isinstance(body, dict) or not body.get("fileId"):
        raise DriveError(f"폴더 생성 응답에 fileId 없음: {name}")
    return body


def _extract_id(meta: dict[str, Any]) -> str:
    for key in ("fileId", "id", "folderId"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            return str(v)
    return ""


def _extract_url(meta: dict[str, Any]) -> str:
    """NAVER WORKS Drive 응답엔 webUrl 키가 없으므로 share URL 패턴으로 조립.

    https://drive.worksmobile.com/drive/web/share/root-folder?resourceKey={fileId}&resourceLocation={loc}
    """
    # 응답에 직접 URL 키가 있으면 우선
    for key in ("webUrl", "url", "shareUrl", "fileUrl"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            return v
    file_id = _extract_id(meta)
    location = meta.get("resourceLocation")
    if file_id and location:
        return (
            "https://drive.worksmobile.com/drive/web/share/root-folder"
            f"?resourceKey={file_id}&resourceLocation={location}"
        )
    return ""


async def ensure_project_folder(
    settings: Settings | None,
    *,
    code: str,
    project_name: str,
) -> tuple[str, str]:
    """`[업무관리]/[CODE]프로젝트명/{1.~7.}` 일괄 생성.

    이미 존재하는 폴더는 재사용. 반환: (root_folder_id, root_folder_url).
    """
    s = settings or get_settings()
    if not s.works_drive_enabled:
        raise DriveError("WORKS_DRIVE_ENABLED=false")
    if not s.works_drive_root_folder_id:
        raise DriveError("WORKS_DRIVE_ROOT_FOLDER_ID 미설정")

    code_norm = (code or "").strip()
    name_norm = (project_name or "").strip()
    if not code_norm or not name_norm:
        raise DriveError("code/project_name 이 비어있음")
    folder_name = f"[{code_norm}]{name_norm}"

    project_meta = await create_folder(
        s, s.works_drive_root_folder_id, folder_name
    )
    project_id = _extract_id(project_meta)
    if not project_id:
        raise DriveError("프로젝트 폴더 fileId를 응답에서 추출하지 못함")

    for sub in SUB_FOLDERS:
        try:
            await create_folder(s, project_id, sub)
        except DriveError as e:
            logger.warning(
                "sub 폴더 생성 실패 (%s/%s): %s", folder_name, sub, e
            )

    return project_id, _extract_url(project_meta)


async def list_sharedrives(settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()
    return await _api(s, "GET", "/sharedrives")
