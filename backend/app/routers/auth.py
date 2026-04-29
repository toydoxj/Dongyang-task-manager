"""인증 라우터 — NAVER WORKS SSO 전용. /me, /users(admin) 만 노출."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User, UserInfo, UserUpdateRequest
from app.security import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
)
from app.services import sso_drive, sso_works
from app.services.employee_link import link_user_to_employee
from app.settings import get_settings

VALID_ROLES = {"admin", "team_lead", "member"}
# 회사 이메일 도메인 강제 (직원만 사용 허용)
ALLOWED_EMAIL_DOMAIN = "@dyce.kr"


def _ensure_company_email(email: str) -> None:
    if not email or not email.lower().endswith(ALLOWED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=400,
            detail=f"이메일은 회사 계정({ALLOWED_EMAIL_DOMAIN})만 사용 가능합니다",
        )

logger = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_info(u: User) -> UserInfo:
    """midas_key 같은 비밀값은 응답에서 제외 (has_midas_key boolean만 노출)."""
    return UserInfo(
        id=u.id,
        username=u.username,
        name=u.name or "",
        email=u.email or "",
        role=u.role or "member",
        status=u.status or "active",
        notion_user_id=u.notion_user_id or "",
        midas_url=u.midas_url or "",
        has_midas_key=bool(u.midas_key),
        work_dir=u.work_dir or "",
        # DB 컬럼이 naive datetime(timezone X)이지만 저장된 값은 UTC.
        # 응답 ISO에 +00:00 표기를 부착해야 frontend가 정확히 KST로 변환.
        last_login_at=(
            u.last_login_at.replace(tzinfo=timezone.utc)
            if u.last_login_at and u.last_login_at.tzinfo is None
            else u.last_login_at
        ),
        auth_provider=u.auth_provider or "password",
    )


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict[str, object]:
    """초기 설정 여부 + SSO 활성 여부 (frontend 로그인 화면에서 NAVER 버튼 표시 결정)."""
    count = db.query(User).count()
    s = get_settings()
    return {
        "initialized": count > 0,
        "user_count": count,
        "works_enabled": bool(
            s.works_enabled and s.works_client_id and s.works_client_secret
        ),
        # NAVER WORKS Drive 탐색기 가상 드라이브 path (frontend의 "탐색기/경로복사" 버튼용).
        # 비어있으면 frontend가 두 버튼 숨김.
        "works_drive_local_root": s.works_drive_local_root,
    }


# ── NAVER WORKS OIDC SSO ──


def _is_https(redirect_uri: str) -> bool:
    return redirect_uri.startswith("https://")


@router.get("/works/login")
async def works_login(
    next: str = Query("/"),
    drive: int = Query(default=0, description="1이면 file scope 추가 요청 (Drive 위임)"),
) -> RedirectResponse:
    """NAVER WORKS authorize URL로 302. state는 HMAC signed (cookie 비사용)."""
    s = get_settings()
    if not s.works_enabled:
        raise HTTPException(status_code=503, detail="NAVER WORKS SSO 비활성")
    if not s.works_client_id or not s.works_redirect_uri:
        raise HTTPException(status_code=503, detail="WORKS 설정 누락")
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    is_drive = drive == 1
    state, _nonce = sso_works.issue_state(
        s.jwt_secret, safe_next, drive=is_drive
    )
    scope = "user.read file" if is_drive else "user.read"
    url = sso_works.authorize_url(s, state, scope=scope)
    return RedirectResponse(url=url, status_code=302)


def _frontend_error_redirect(s, message: str) -> RedirectResponse:
    base = (s.frontend_base_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=400, detail=message)
    qs = urlencode({"error": message})
    return RedirectResponse(url=f"{base}/login?{qs}", status_code=302)


@router.get("/works/callback")
async def works_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """NAVER WORKS authorize 응답 처리. signed state 검증 후 token 교환."""
    s = get_settings()
    if not s.works_enabled:
        raise HTTPException(status_code=503, detail="NAVER WORKS SSO 비활성")
    if error:
        return _frontend_error_redirect(s, f"NAVER WORKS 응답 오류: {error}")
    if not code or not state:
        return _frontend_error_redirect(s, "code/state 누락")

    try:
        state_data = sso_works.verify_state(s.jwt_secret, state)
    except sso_works.SSOError as e:
        return _frontend_error_redirect(s, str(e))

    safe_next = state_data.get("x", "/")
    if not isinstance(safe_next, str) or not safe_next.startswith("/"):
        safe_next = "/"
    is_drive_flow = state_data.get("d") == 1

    out_tokens: dict[str, object] = {}
    try:
        user = await sso_works.process_callback(
            db, code=code, settings=s, out_tokens=out_tokens
        )
    except sso_works.SSOError as e:
        logger.warning("SSO 처리 실패: %s", e)
        return _frontend_error_redirect(s, str(e))
    except Exception:  # noqa: BLE001
        logger.exception("SSO 처리 중 예외")
        return _frontend_error_redirect(s, "SSO 처리 중 오류가 발생했습니다")

    # Drive 위임 흐름: admin이 file scope를 동의했고 응답에 file이 포함되면 토큰 보관
    if is_drive_flow:
        if user.role != "admin":
            return _frontend_error_redirect(
                s, "Drive 위임은 관리자만 가능합니다"
            )
        granted_scope = str(out_tokens.get("scope", ""))
        if "file" not in granted_scope.split():
            return _frontend_error_redirect(
                s,
                f"Drive scope 'file'이 부여되지 않음 (received='{granted_scope}'). "
                "콘솔에서 'file' scope 체크 + 저장 확인 필요",
            )
        try:
            sso_drive.save_creds(
                db,
                access_token=str(out_tokens.get("access_token", "")),
                refresh_token=str(out_tokens.get("refresh_token", "")),
                expires_in=int(out_tokens.get("expires_in", 3600) or 3600),
                scope=granted_scope,
                granted_by_user_id=user.id,
                granted_by_email=user.email or "",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Drive 토큰 저장 실패")
            return _frontend_error_redirect(
                s, "Drive 토큰 저장 실패"
            )

    sid = uuid4().hex
    user.session_id = sid
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_token(user.username, user.role, sid)
    info = _to_info(user)
    user_b64 = base64.urlsafe_b64encode(
        json.dumps(info.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    base = (s.frontend_base_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="FRONTEND_BASE_URL 미설정")
    # Drive 위임 흐름: drive_connected=1 query를 next 페이지에 붙여 알림
    if is_drive_flow:
        sep = "&" if "?" in safe_next else "?"
        return RedirectResponse(
            url=(
                f"{base}/auth/works/callback"
                f"#token={token}&user={user_b64}&next={safe_next}{sep}drive_connected=1"
            ),
            status_code=302,
        )
    target = (
        f"{base}/auth/works/callback#token={token}"
        f"&user={user_b64}&next={safe_next}"
    )
    return RedirectResponse(url=target, status_code=302)


@router.get("/me", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)) -> UserInfo:
    return _to_info(user)


@router.get("/me/midas")
def get_my_midas_credentials(user: User = Depends(get_current_user)) -> dict:
    """본인의 MIDAS 자격 반환 (DY_MIDAS Electron sidecar 용).

    midas_key는 일반 /me에는 노출되지 않으나 본 endpoint는 인증된 본인에게만
    자기 값을 반환. SSO 위임 패턴에서 sidecar가 사용자별 설정을 적용하는 데 사용.
    """
    return {
        "midas_url": user.midas_url or "",
        "midas_key": user.midas_key or "",
        "work_dir": user.work_dir or "",
    }


@router.put("/me", response_model=UserInfo)
def update_me(
    body: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserInfo:
    """SSO 전용이라 password 필드는 무시 (이름·이메일·MIDAS 설정만 갱신)."""
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = str(body.email)
    if body.notion_user_id is not None:
        user.notion_user_id = body.notion_user_id
    if body.midas_url is not None:
        user.midas_url = body.midas_url
    if body.midas_key is not None:
        user.midas_key = body.midas_key
    if body.work_dir is not None:
        user.work_dir = body.work_dir
    db.commit()
    db.refresh(user)
    return _to_info(user)


# ── 관리자 (사용자 관리는 SSO로 자동 생성된 계정에 대해서만) ──


@router.get("/users", response_model=list[UserInfo])
def list_users(
    admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[UserInfo]:
    return [_to_info(u) for u in db.query(User).order_by(User.id).all()]


@router.post("/users/{user_id}/approve", response_model=UserInfo)
def approve_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    user.status = "active"
    # 승인 시점에 직원 매칭 재시도 (admin이 employee 이메일을 그 사이에 추가했을 수 있음)
    link_user_to_employee(db, user)
    db.commit()
    db.refresh(user)
    return _to_info(user)


class RoleUpdate(BaseModel):
    role: Literal["admin", "team_lead", "member"]


@router.patch("/users/{user_id}/role", response_model=UserInfo)
def set_user_role(
    user_id: int,
    body: RoleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    """admin이 사용자 권한 변경. 자기 자신을 강등(admin → 다른 role)할 때는
    다른 admin이 최소 1명 남아 있어야 한다."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="잘못된 role")
    if (
        admin.id == user.id
        and user.role == "admin"
        and body.role != "admin"
    ):
        other_admin = (
            db.query(User)
            .filter(User.role == "admin", User.id != user.id)
            .first()
        )
        if not other_admin:
            raise HTTPException(
                status_code=400, detail="마지막 관리자는 강등할 수 없습니다"
            )
    user.role = body.role
    db.commit()
    db.refresh(user)
    return _to_info(user)


class AdminUserUpdate(BaseModel):
    """admin이 다른 사용자 정보 수정 (비밀번호 reset은 별도 흐름)."""

    name: str | None = None
    email: str | None = None
    notion_user_id: str | None = None


@router.patch("/users/{user_id}", response_model=UserInfo)
def admin_update_user(
    user_id: int,
    body: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        _ensure_company_email(body.email)
        user.email = body.email
        link_user_to_employee(db, user)  # 이메일 변경 시 직원 매칭 재시도
    if body.notion_user_id is not None:
        user.notion_user_id = body.notion_user_id
    db.commit()
    db.refresh(user)
    return _to_info(user)


@router.post("/users/{user_id}/reject")
def reject_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    user.status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="자기 자신은 삭제할 수 없습니다"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다"
        )
    db.delete(user)
    db.commit()
    return {"status": "deleted"}
