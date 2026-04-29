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
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.drive_creds import DriveCredential
from app.settings import Settings, get_settings

logger = logging.getLogger("sso.drive")

_TOKEN_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/token"
_AUTHORIZE_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/authorize"
_HTTP_TIMEOUT = 15.0
_DRIVE_SCOPE = "file"
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


# ── Authorize / token 교환 (admin 동의 흐름) ──


def authorize_url(settings: Settings, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.works_client_id,
        "redirect_uri": settings.works_drive_redirect_uri,
        "scope": _DRIVE_SCOPE,
        "state": state,
    }
    return f"{_AUTHORIZE_ENDPOINT}?{urlencode(params)}"


async def exchange_code(
    settings: Settings, code: str
) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.works_drive_redirect_uri,
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
            raise DriveError(f"token endpoint 네트워크 오류: {e}") from e
        if resp.status_code != 200:
            logger.warning(
                "drive code 교환 실패: %s %s", resp.status_code, resp.text
            )
            raise DriveError(f"토큰 교환 실패 ({resp.status_code})")
        return resp.json()


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
    sd = settings.works_drive_sharedrive_id
    if not sd:
        raise DriveError("WORKS_DRIVE_SHAREDRIVE_ID 미설정")
    try:
        body = await _api(
            settings,
            "GET",
            f"/sharedrives/{sd}/files/{parent_id}/children",
            params={"fileType": "folder"},
        )
    except DriveError:
        body = await _api(
            settings,
            "GET",
            f"/sharedrives/{sd}/files",
            params={"parentFolderId": parent_id, "fileType": "folder"},
        )
    items = body.get("files") or body.get("items") or body.get("children") or []
    for it in items:
        item_name = it.get("fileName") or it.get("name") or ""
        if item_name == name:
            return it
    return None


async def create_folder(
    settings: Settings, parent_id: str, name: str
) -> dict[str, Any]:
    existing = await find_child_folder(settings, parent_id, name)
    if existing is not None:
        return existing
    sd = settings.works_drive_sharedrive_id
    body = await _api(
        settings,
        "POST",
        f"/sharedrives/{sd}/files",
        json={
            "fileName": name,
            "parentFolderId": parent_id,
            "fileType": "folder",
        },
    )
    return body


def _extract_url(meta: dict[str, Any]) -> str:
    for key in ("webUrl", "url", "shareUrl", "fileUrl"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _extract_id(meta: dict[str, Any]) -> str:
    for key in ("fileId", "id", "folderId"):
        v = meta.get(key)
        if isinstance(v, str) and v:
            return str(v)
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
