"""JWT 토큰 + 패스워드 해싱 + 인증 의존성."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User, UserSession
from app.settings import get_settings

_bearer = HTTPBearer(auto_error=False)

# PR-BH: JWT cookie 이름. backend가 set/delete + frontend가 credentials:include로 자동 첨부.
JWT_COOKIE_NAME = "dy_jwt"

# PR-BI: header 인증 사용 telemetry. web은 cookie 단독으로 전환 후 header 사용량이
# 0(또는 dy-midas만)으로 수렴해야 한다. Render Logs에서 "auth_via_header" 검색.
_auth_logger = logging.getLogger("app.auth")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(
    username: str,
    role: str,
    session_id: str = "",
    client: str = "task",
) -> str:
    s = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "sid": session_id,
        "cli": client,
        "exp": expire,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    dy_jwt: str | None = Cookie(default=None),
) -> User:
    # PR-BH (Phase 4-G 1단계): Authorization header 우선 + 없으면 dy_jwt cookie fallback.
    # 점진 마이그레이션 동안 두 인증 채널 모두 허용. 2단계에서 header 비활성 가능.
    via_header = cred is not None
    raw_token = cred.credentials if via_header else dy_jwt
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요합니다"
        )
    try:
        payload = decode_token(raw_token)
        username: str = payload.get("sub", "")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 토큰"
            )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었거나 유효하지 않습니다",
        ) from exc

    # PR-BI: header 인증 telemetry. cookie 채널이 정상이면 web client(cli=task)는
    # 점진 0으로 수렴해야 한다. dy-midas는 한동안 header 유지 예정.
    if via_header:
        _auth_logger.info(
            "auth_via_header user=%s cli=%s",
            username,
            payload.get("cli", "") or "?",
        )

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="사용자를 찾을 수 없습니다"
        )

    # 이중 로그인 방지: client 단위로 활성 sid 비교.
    # - cli claim 있는 토큰: user_sessions(user_id, client) 조회.
    # - cli claim 없는 레거시 토큰: users.session_id 와 비교 (기존 동작 유지).
    token_sid = payload.get("sid", "")
    token_cli = payload.get("cli", "")
    if token_sid:
        if token_cli:
            sess = (
                db.query(UserSession)
                .filter(
                    UserSession.user_id == user.id,
                    UserSession.client == token_cli,
                )
                .first()
            )
            if sess is None or sess.session_id != token_sid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="다른 기기에서 로그인되었습니다",
                )
        else:
            if user.session_id and token_sid != user.session_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="다른 기기에서 로그인되었습니다",
                )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다"
        )
    return user


def require_admin_or_lead(user: User = Depends(get_current_user)) -> User:
    """admin 또는 team_lead 만 접근 가능 (read-only가 많은 경우 사용)."""
    if user.role not in {"admin", "team_lead"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 또는 팀장 권한이 필요합니다",
        )
    return user


def require_admin_or_manager(user: User = Depends(get_current_user)) -> User:
    """admin 또는 manager(관리팀) 만 접근 가능 — 운영 관리(계약분담 등)용."""
    if user.role not in {"admin", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 또는 관리팀 권한이 필요합니다",
        )
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    """admin / team_lead / manager — 운영 편집 권한 (프로젝트 일반 편집·계약분담 등).

    member는 read-only.
    """
    if user.role not in {"admin", "team_lead", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="편집 권한이 필요합니다 (admin/팀장/관리팀)",
        )
    return user
