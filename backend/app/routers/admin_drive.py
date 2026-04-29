"""/api/admin/drive — admin이 NAVER WORKS Drive 토큰을 위임받는 흐름.

NAVER WORKS Console의 redirect URI 슬롯이 한정적이라 SSO callback과 통합.
admin이 /api/admin/drive/connect를 부르면 그냥 SSO login에 ?drive=1 추가해
같은 redirect URI(/api/auth/works/callback)로 돌아오도록 redirect.
SSO callback이 state.d==1을 보고 admin·scope 검증 후 drive_credentials 저장.

GET /api/admin/drive/connect → 302 to /api/auth/works/login?drive=1
GET /api/admin/drive/status   → 토큰 상태 (admin only)
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
from app.settings import get_settings

logger = logging.getLogger("admin.drive")
router = APIRouter(prefix="/admin/drive", tags=["admin-drive"])


@router.get("/connect")
def connect(
    next: str = Query("/admin/drive"),
    _admin: User = Depends(require_admin),
) -> RedirectResponse:
    """admin 인증 후 SSO login에 drive 플래그 붙여 redirect."""
    s = get_settings()
    if not s.works_enabled:
        raise HTTPException(status_code=503, detail="NAVER WORKS SSO 비활성")
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/admin/drive"
    qs = urlencode({"drive": "1", "next": safe_next})
    # SSO login은 /api/auth/works/login 에 있음 (메인 라우터)
    return RedirectResponse(url=f"/api/auth/works/login?{qs}", status_code=302)


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
