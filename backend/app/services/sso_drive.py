"""NAVER WORKS Drive — 프로젝트별 폴더 자동 생성 (Phase 2).

흐름:
1. Service Account JWT(RS256) 자체 서명 → assertion으로 token endpoint POST
2. access_token 발급 (1h TTL, in-memory 캐시)
3. 공유 드라이브에 폴더 생성·조회 (idempotent)

설계 원칙:
- 외부 API 실패가 본 백엔드의 다른 흐름(프로젝트 생성 등)을 막지 않도록 SSOError로 감쌈
- access_token은 process 단일 캐시 (만료 60초 전 갱신)
- 폴더 생성은 idempotent — 같은 이름이 부모 아래 이미 있으면 그 fileId 재사용
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from jose import jwt

from app.settings import Settings, get_settings

logger = logging.getLogger("sso.drive")

_TOKEN_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/token"
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


# ── access_token 캐시 ──


class _TokenCache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._token: str = ""
        self._expires_at: float = 0.0

    async def get(self, settings: Settings) -> str:
        async with self._lock:
            now = time.monotonic()
            if self._token and now < self._expires_at - 60:
                return self._token
            token, expires_in = await _request_access_token(settings)
            self._token = token
            self._expires_at = now + max(60, int(expires_in))
            return self._token

    def invalidate(self) -> None:
        self._token = ""
        self._expires_at = 0.0


_cache = _TokenCache()


# ── JWT 발급 + token 교환 ──


def _build_assertion(settings: Settings) -> str:
    """Service Account JWT(RS256) 발급. payload는 NAVER WORKS spec.

    iss = client_id (Console의 OAuth client id)
    sub = service account id (Console에서 발급)
    iat / exp = 표준 OAuth assertion (~1h)
    """
    if not settings.works_private_key:
        raise DriveError("WORKS_PRIVATE_KEY 미설정")
    if not settings.works_service_account_id:
        raise DriveError("WORKS_SERVICE_ACCOUNT_ID 미설정")
    if not settings.works_client_id:
        raise DriveError("WORKS_CLIENT_ID 미설정")

    now = int(time.time())
    payload = {
        "iss": settings.works_client_id,
        "sub": settings.works_service_account_id,
        "iat": now,
        "exp": now + 3600,
    }
    # PEM의 줄바꿈이 환경변수로 \n 문자열로 들어오는 경우 복원
    pem = settings.works_private_key.replace("\\n", "\n")
    return jwt.encode(payload, pem, algorithm="RS256")


async def _request_access_token(settings: Settings) -> tuple[str, int]:
    """JWT assertion → access_token. 응답 (token, expires_in)."""
    if not settings.works_client_secret:
        raise DriveError("WORKS_CLIENT_SECRET 미설정")
    assertion = _build_assertion(settings)
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": settings.works_client_id,
        "client_secret": settings.works_client_secret,
        "assertion": assertion,
        "scope": _DRIVE_SCOPE,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                _TOKEN_ENDPOINT,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            raise DriveError(f"token endpoint 네트워크 오류: {e}") from e
        if resp.status_code != 200:
            logger.warning(
                "service account token 발급 실패: %s %s",
                resp.status_code,
                resp.text,
            )
            raise DriveError(
                f"Service Account 토큰 발급 실패 ({resp.status_code})"
            )
        body = resp.json()
        token = str(body.get("access_token", ""))
        expires_in = int(body.get("expires_in", 3600))
        if not token:
            raise DriveError("토큰 응답에 access_token이 없음")
        return token, expires_in


# ── Drive HTTP helper ──


async def _api(
    settings: Settings,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """access_token을 자동 부착해 worksapis.com에 호출. 401 시 1회 재발급 후 retry."""
    url = f"{settings.works_api_base.rstrip('/')}{path}"

    async def _call(token: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            return await client.request(
                method,
                url,
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )

    token = await _cache.get(settings)
    resp = await _call(token)
    if resp.status_code == 401:
        # 토큰 만료/회수 가능성 → 1회 재시도
        _cache.invalidate()
        token = await _cache.get(settings)
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
    """parent 아래에서 같은 이름의 폴더가 있으면 그 metadata 반환, 없으면 None.

    NAVER WORKS Drive API의 list 호출 path는 PoC에서 확정. 후보:
    - /sharedrives/{sd}/files/{parent}/children
    - /sharedrives/{sd}/files?parentFolderId={parent}
    환경변수로 sharedrive id를 받기 때문에 path는 그에 맞춰 구성.
    """
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
        # children path가 다를 가능성 → 다른 후보로 fallback (PoC 후 단일 path로 정착)
        body = await _api(
            settings,
            "GET",
            f"/sharedrives/{sd}/files",
            params={"parentFolderId": parent_id, "fileType": "folder"},
        )

    # 응답 schema는 NAVER WORKS spec에 따라 'files' 또는 'items' 둘 중 하나로 옴
    items = body.get("files") or body.get("items") or body.get("children") or []
    for it in items:
        item_name = it.get("fileName") or it.get("name") or ""
        if item_name == name:
            return it
    return None


async def create_folder(
    settings: Settings, parent_id: str, name: str
) -> dict[str, Any]:
    """parent 아래 폴더 생성. 이미 있으면 그 metadata 반환 (idempotent)."""
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


# ── 외부에 노출되는 high-level API ──


async def ensure_project_folder(
    settings: Settings | None,
    *,
    code: str,
    project_name: str,
) -> tuple[str, str]:
    """`[업무관리]/[CODE]프로젝트명/{1.건축도면, ..., 7.기타}` 일괄 생성.

    이미 존재하는 폴더는 그대로 사용.
    반환: (root_folder_id, root_folder_url) — 프로젝트 row에 저장할 값.
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

    # 7개 sub 폴더 — 직렬 생성 (rate limit 보호)
    for sub in SUB_FOLDERS:
        try:
            await create_folder(s, project_id, sub)
        except DriveError as e:
            # 일부 sub 폴더 실패해도 메인 폴더는 살아있음 — 로그 후 계속
            logger.warning("sub 폴더 생성 실패 (%s/%s): %s", folder_name, sub, e)

    return project_id, _extract_url(project_meta)


async def list_sharedrives(settings: Settings | None = None) -> dict[str, Any]:
    """PoC/디버깅용 — 공유 드라이브 목록 조회."""
    s = settings or get_settings()
    return await _api(s, "GET", "/sharedrives")
