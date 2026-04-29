"""/api/admin/drive — admin이 NAVER WORKS Drive 토큰을 위임받는 흐름.

Drive API는 user 토큰만 받으므로 admin 1명이 한 번 file scope 동의 →
DB의 drive_credentials(id=1)에 보관 → 모든 자동 폴더 생성에 재사용.

GET /api/admin/drive/connect
    → admin 인증 후 NAVER WORKS authorize URL로 302 (signed state)

GET /api/admin/drive/callback
    → code 교환 후 drive_credentials 저장. signed state 검증.
    → frontend의 /admin 페이지로 redirect (성공 message 또는 error query)

GET /api/admin/drive/status
    → 토큰 보유 여부, 만료까지 남은 시간, 동의한 admin 정보 (admin only)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.drive_creds import DriveCredential
from app.security import require_admin
from app.services import sso_drive, sso_works
from app.settings import get_settings

logger = logging.getLogger("admin.drive")
router = APIRouter(prefix="/admin/drive", tags=["admin-drive"])


@router.get("/connect")
def connect(
    next: str = Query("/admin"),
    admin: User = Depends(require_admin),
) -> RedirectResponse:
    """admin 인증 후 NAVER WORKS Drive authorize URL로 302."""
    s = get_settings()
    if not s.works_client_id or not s.works_client_secret:
        raise HTTPException(status_code=503, detail="WORKS 클라이언트 미설정")
    if not s.works_drive_redirect_uri:
        raise HTTPException(
            status_code=503, detail="WORKS_DRIVE_REDIRECT_URI 미설정"
        )
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/admin"
    # state에 admin user.id를 담아 callback에서 누가 동의했는지 추적
    state, _nonce = sso_works.issue_state(
        s.jwt_secret, f"{safe_next}|uid={admin.id}|email={admin.email}"
    )
    return RedirectResponse(
        url=sso_drive.authorize_url(s, state), status_code=302
    )


@router.get("/callback")
async def callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """NAVER WORKS authorize 응답 처리. 성공 시 토큰 저장 후 frontend로 302."""
    s = get_settings()
    base = (s.frontend_base_url or "").rstrip("/")

    def _err(msg: str) -> RedirectResponse:
        if not base:
            raise HTTPException(status_code=400, detail=msg)
        qs = urlencode({"drive_error": msg})
        return RedirectResponse(url=f"{base}/admin?{qs}", status_code=302)

    if error:
        return _err(f"NAVER WORKS 응답 오류: {error}")
    if not code or not state:
        return _err("code/state 누락")

    try:
        state_data = sso_works.verify_state(s.jwt_secret, state)
    except sso_works.SSOError as e:
        return _err(str(e))

    next_field = state_data.get("x", "/admin")
    safe_next = next_field.split("|", 1)[0] if isinstance(next_field, str) else "/admin"
    granted_uid: int | None = None
    granted_email = ""
    if isinstance(next_field, str):
        for part in next_field.split("|")[1:]:
            if part.startswith("uid="):
                try:
                    granted_uid = int(part[4:])
                except ValueError:
                    pass
            elif part.startswith("email="):
                granted_email = part[6:]

    try:
        body = await sso_drive.exchange_code(s, code)
    except sso_drive.DriveError as e:
        return _err(str(e))

    access_token = body.get("access_token", "")
    refresh_token = body.get("refresh_token", "")
    expires_in = int(body.get("expires_in", 3600))
    scope = str(body.get("scope", ""))
    if not access_token:
        return _err("access_token이 응답에 없습니다")
    if "file" not in scope.split():
        return _err(
            f"부여된 scope에 'file'이 없습니다 (received='{scope}'). 콘솔 scope 확인 필요"
        )

    sso_drive.save_creds(
        db,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        scope=scope,
        granted_by_user_id=granted_uid,
        granted_by_email=granted_email,
    )
    db.commit()

    if not base:
        return RedirectResponse(
            url="/", status_code=302
        )  # 로컬 개발용 fallback
    qs = urlencode({"drive_connected": "1"})
    return RedirectResponse(url=f"{base}{safe_next}?{qs}", status_code=302)


@router.get("/status")
def status(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """admin이 현재 Drive 위임 상태 확인."""
    row = db.get(DriveCredential, 1)
    if row is None or not row.access_token:
        return {"connected": False}
    expires_at = row.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    seconds_left: int | None = None
    if expires_at:
        seconds_left = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    return {
        "connected": True,
        "scope": row.scope,
        "granted_by_email": row.granted_by_email,
        "granted_by_user_id": row.granted_by_user_id,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "seconds_left": seconds_left,
        "has_refresh_token": bool(row.refresh_token),
        "updated_at": (
            row.updated_at.replace(tzinfo=UTC).isoformat()
            if row.updated_at and row.updated_at.tzinfo is None
            else (row.updated_at.isoformat() if row.updated_at else None)
        ),
    }
