"""인증 라우터 — 회원가입(최초 관리자/승인 신청), 로그인, 사용자 관리."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

VALID_ROLES = {"admin", "team_lead", "member"}

# 회사 이메일 도메인 강제 (직원만 가입 허용)
ALLOWED_EMAIL_DOMAIN = "@dyce.kr"


def _ensure_company_email(email: str) -> None:
    if not email or not email.lower().endswith(ALLOWED_EMAIL_DOMAIN):
        raise HTTPException(
            status_code=400,
            detail=f"이메일은 회사 계정({ALLOWED_EMAIL_DOMAIN})만 사용 가능합니다",
        )


from app.db import get_db
from app.models.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    User,
    UserInfo,
    UserUpdateRequest,
)
from app.security import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from app.services import sso_works
from app.services.employee_link import link_user_to_employee
from app.settings import get_settings

logger = logging.getLogger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# SSO state/nonce 쿠키 — backend 도메인(api.dyce.kr)에만 부착, callback 직후 삭제
_SSO_STATE_COOKIE = "works_state"
_SSO_NONCE_COOKIE = "works_nonce"
_SSO_NEXT_COOKIE = "works_next"
_SSO_COOKIE_MAX_AGE = 600  # 10분


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
    }


# ── NAVER WORKS OIDC SSO ──


def _is_https(redirect_uri: str) -> bool:
    return redirect_uri.startswith("https://")


@router.get("/works/login")
async def works_login(next: str = Query("/")) -> RedirectResponse:
    """NAVER WORKS authorize URL로 302. state/nonce는 쿠키로 보존."""
    s = get_settings()
    if not s.works_enabled:
        raise HTTPException(status_code=503, detail="NAVER WORKS SSO 비활성")
    if not s.works_client_id or not s.works_redirect_uri:
        raise HTTPException(status_code=503, detail="WORKS 설정 누락")
    state, nonce = sso_works.make_state_and_nonce()
    url = sso_works.authorize_url(s, state, nonce)

    secure = _is_https(s.works_redirect_uri)
    resp = RedirectResponse(url=url, status_code=302)
    cookie_kwargs = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "max_age": _SSO_COOKIE_MAX_AGE,
        "path": "/api/auth/works",
    }
    resp.set_cookie(_SSO_STATE_COOKIE, state, **cookie_kwargs)
    resp.set_cookie(_SSO_NONCE_COOKIE, nonce, **cookie_kwargs)
    # next 경로는 frontend로 그대로 전달용. 외부 redirect 방지를 위해 / 시작만 허용
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    resp.set_cookie(_SSO_NEXT_COOKIE, safe_next, **cookie_kwargs)
    return resp


def _delete_sso_cookies(resp: RedirectResponse, *, secure: bool) -> None:
    # 동일한 (path, secure, samesite)로 set한 쿠키는 동일 속성으로 삭제해야
    # 일부 브라우저에서 정상 제거됨.
    for name in (_SSO_STATE_COOKIE, _SSO_NONCE_COOKIE, _SSO_NEXT_COOKIE):
        resp.delete_cookie(
            name, path="/api/auth/works", secure=secure, samesite="lax"
        )


def _frontend_error_redirect(s, message: str) -> RedirectResponse:
    base = (s.frontend_base_url or "").rstrip("/")
    if not base:
        # frontend_base_url 미설정 시 단순 JSON 에러 (E2E 디버깅 편의)
        raise HTTPException(status_code=400, detail=message)
    qs = urlencode({"error": message})
    resp = RedirectResponse(url=f"{base}/login?{qs}", status_code=302)
    _delete_sso_cookies(resp, secure=_is_https(s.works_redirect_uri))
    return resp


@router.get("/works/callback")
async def works_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    works_state: str | None = Cookie(default=None, alias=_SSO_STATE_COOKIE),
    works_nonce: str | None = Cookie(default=None, alias=_SSO_NONCE_COOKIE),
    works_next: str | None = Cookie(default=None, alias=_SSO_NEXT_COOKIE),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """NAVER WORKS authorize 응답 처리. 성공 시 frontend로 fragment redirect."""
    s = get_settings()
    if not s.works_enabled:
        raise HTTPException(status_code=503, detail="NAVER WORKS SSO 비활성")
    if error:
        return _frontend_error_redirect(s, f"NAVER WORKS 응답 오류: {error}")
    if not code or not state:
        return _frontend_error_redirect(s, "code/state 누락")
    if not works_state or state != works_state:
        return _frontend_error_redirect(s, "state 불일치 (CSRF 의심)")
    if not works_nonce:
        return _frontend_error_redirect(s, "nonce 쿠키 누락 — 다시 시도해 주세요")

    try:
        user = await sso_works.process_callback(
            db, code=code, expected_nonce=works_nonce, settings=s
        )
    except sso_works.SSOError as e:
        logger.warning("SSO 처리 실패: %s", e)
        return _frontend_error_redirect(s, str(e))
    except Exception:  # noqa: BLE001
        logger.exception("SSO 처리 중 예외")
        return _frontend_error_redirect(s, "SSO 처리 중 오류가 발생했습니다")

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
    safe_next = works_next if works_next and works_next.startswith("/") else "/"
    # fragment(#)에 토큰 전달 — 서버·프록시 로그 노출 회피
    target = (
        f"{base}/auth/works/callback#token={token}"
        f"&user={user_b64}&next={safe_next}"
    )
    resp = RedirectResponse(url=target, status_code=302)
    _delete_sso_cookies(resp, secure=_is_https(s.works_redirect_uri))
    return resp


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """최초 1인만 직접 등록(관리자), 이후엔 /auth/request 또는 /auth/users 사용."""
    if db.query(User).count() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자를 통해 등록해주세요"
        )
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    _ensure_company_email(str(body.email))

    sid = uuid4().hex
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="admin",
        status="active",
        session_id=sid,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.username, user.role, sid)
    return TokenResponse(access_token=token, user=_to_info(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
        )
    if user.status == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="가입 승인 대기 중입니다. 관리자에게 문의하세요.",
        )
    if user.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="가입이 거절되었습니다."
        )

    sid = uuid4().hex
    user.session_id = sid
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_token(user.username, user.role, sid)
    return TokenResponse(access_token=token, user=_to_info(user))


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
    if body.name is not None:
        user.name = body.name
    if body.email is not None:
        user.email = str(body.email)
    if body.password is not None:
        user.password = hash_password(body.password)
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


# ── 관리자/공개 ──


@router.post("/request")
def request_join(body: RegisterRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    """가입 신청 — 이메일이 직원 명부에 있으면 즉시 자동 승인 + 매칭, 아니면 pending."""
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    _ensure_company_email(str(body.email))
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="member",
        status="pending",
    )
    db.add(user)
    db.flush()  # user.id 확보
    emp = link_user_to_employee(db, user)
    if emp is not None:
        user.status = "active"
        db.commit()
        return {
            "status": "active",
            "message": f"직원 명부에서 확인되어 자동 승인되었습니다 ({emp.team or emp.position}).",
        }
    db.commit()
    return {
        "status": "pending",
        "message": "가입 신청이 완료되었습니다. 관리자 승인을 기다려주세요.",
    }


@router.post("/users", response_model=UserInfo)
def admin_create_user(
    body: RegisterRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserInfo:
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 존재하는 아이디입니다"
        )
    _ensure_company_email(str(body.email))
    user = User(
        username=body.username,
        password=hash_password(body.password),
        name=body.name,
        email=str(body.email),
        role="member",
        status="active",
    )
    db.add(user)
    db.flush()
    link_user_to_employee(db, user)
    db.commit()
    db.refresh(user)
    return _to_info(user)


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
