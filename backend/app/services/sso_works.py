"""NAVER WORKS OAuth 2.0 SSO — Phase 1.

NAVER WORKS는 OIDC discovery(/.well-known/openid-configuration)를 표준 path에
노출하지 않으므로 endpoint를 settings에서 직접 사용.
ID token RS256 검증 대신 access_token으로 UserInfo API(/users/me)를 호출해
사용자 식별. 도메인 차단은 응답의 domainId로 처리.

state는 cookie 의존성을 피하기 위해 HMAC-SHA256 signed token으로 인코딩.
(cross-site redirect 후 SameSite cookie가 일부 환경에서 누락되는 문제 회피)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.models.auth import User
from app.security import hash_password
from app.services.employee_link import link_user_to_employee
from app.settings import Settings, get_settings

logger = logging.getLogger("sso.works")

ALLOWED_EMAIL_DOMAIN = "@dyce.kr"

_HTTP_TIMEOUT = 10.0
_STATE_TTL_S = 600  # 10분


class SSOError(Exception):
    """SSO 흐름 중 사용자에게 노출 가능한 에러."""


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_state(jwt_secret: str, next_path: str) -> tuple[str, str]:
    """signed state(HMAC) + nonce 발급. cookie 없이도 검증 가능.

    state payload: {nonce, ts, next} → JSON → base64url
    sig: HMAC-SHA256(secret, payload) → base64url
    state token: payload.sig
    """
    nonce = secrets.token_urlsafe(32)
    payload = json.dumps(
        {"n": nonce, "t": int(time.time()), "x": next_path or "/"},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    payload_b64 = _b64url_encode(payload)
    sig = hmac.new(
        jwt_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}", nonce


def verify_state(jwt_secret: str, state: str) -> dict[str, Any]:
    """state token 검증 + 만료 확인. 실패 시 SSOError."""
    if not state or "." not in state:
        raise SSOError("state 형식 오류")
    payload_b64, sig_b64 = state.rsplit(".", 1)
    expected = hmac.new(
        jwt_secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    try:
        actual = _b64url_decode(sig_b64)
    except Exception as e:
        raise SSOError("state 디코드 실패") from e
    if not hmac.compare_digest(expected, actual):
        raise SSOError("state 서명 불일치 (CSRF 의심)")
    try:
        data = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as e:
        raise SSOError("state payload 파싱 실패") from e
    ts = int(data.get("t", 0))
    if ts <= 0 or time.time() - ts > _STATE_TTL_S:
        raise SSOError("state 만료 — 다시 시도해 주세요")
    return data


def authorize_url(settings: Settings, state: str) -> str:
    """NAVER WORKS authorize URL 생성. discovery 호출 없음."""
    params = {
        "response_type": "code",
        "client_id": settings.works_client_id,
        "redirect_uri": settings.works_redirect_uri,
        "scope": "user.read",  # UserInfo API 호출 권한
        "state": state,
    }
    return f"{settings.works_authorize_endpoint}?{urlencode(params)}"


async def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.works_redirect_uri,
        "client_id": settings.works_client_id,
        "client_secret": settings.works_client_secret,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.post(
                settings.works_token_endpoint,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            logger.warning("token endpoint 네트워크 오류: %s", e)
            raise SSOError("토큰 교환 실패 (네트워크)") from e
        if resp.status_code != 200:
            logger.warning(
                "token endpoint 응답 오류: %s %s", resp.status_code, resp.text
            )
            raise SSOError(f"토큰 교환 실패 ({resp.status_code})")
        return resp.json()


async def fetch_user_info(
    settings: Settings, access_token: str
) -> dict[str, Any]:
    """access_token으로 NAVER WORKS UserInfo API 호출."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        try:
            resp = await client.get(
                settings.works_userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as e:
            logger.warning("userinfo 네트워크 오류: %s", e)
            raise SSOError("사용자 정보 조회 실패 (네트워크)") from e
        if resp.status_code != 200:
            logger.warning(
                "userinfo 응답 오류: %s %s", resp.status_code, resp.text
            )
            raise SSOError(f"사용자 정보 조회 실패 ({resp.status_code})")
        return resp.json()


def _extract_name(info: dict[str, Any]) -> str:
    """NAVER WORKS UserInfo의 이름을 한국어 표기로 합성."""
    name_obj = info.get("userName")
    if isinstance(name_obj, dict):
        last = (name_obj.get("lastName") or "").strip()
        first = (name_obj.get("firstName") or "").strip()
        # 한국어: 성+이름 (공백 없음)
        if last or first:
            return f"{last}{first}".strip()
    # fallback
    for key in ("displayName", "name", "preferred_username"):
        v = info.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _domain_matches(info: dict[str, Any], expected: str) -> bool:
    """UserInfo 응답의 domainId 검증. expected가 비면 검증 생략 (개발 편의)."""
    if not expected:
        return True
    for key in ("domainId", "domain_id", "domain"):
        v = info.get(key)
        if v is None:
            continue
        if str(v) == str(expected):
            return True
    return False


def upsert_user(
    db: Session,
    *,
    works_user_id: str,
    email: str,
    name: str,
    blocked_emails: set[str] | None = None,
) -> tuple[User, bool]:
    """works_user_id 우선, email fallback. 신규는 자동 active+member.

    blocked_emails(소문자)에 포함되는 계정은 SSOError로 거부 (마스터/시스템 계정 차단).
    """
    email_norm = (email or "").strip().lower()
    if not email_norm.endswith(ALLOWED_EMAIL_DOMAIN):
        raise SSOError(
            f"이메일은 회사 계정({ALLOWED_EMAIL_DOMAIN})만 사용 가능합니다"
        )
    if blocked_emails and email_norm in blocked_emails:
        raise SSOError(
            f"{email_norm}은(는) 사용할 수 없는 계정입니다 (관리자에게 문의하세요)"
        )

    user = db.query(User).filter(User.works_user_id == works_user_id).first()
    if user is not None:
        if not user.name and name:
            user.name = name
        if not user.email and email_norm:
            user.email = email_norm
        return user, False

    user = db.query(User).filter(User.email == email_norm).first()
    if user is not None:
        user.works_user_id = works_user_id
        if user.auth_provider == "password":
            user.auth_provider = "both"
        if not user.name and name:
            user.name = name
        return user, False

    base_username = email_norm.split("@", 1)[0] or "user"
    username = base_username
    suffix = 1
    while db.query(User).filter(User.username == username).first() is not None:
        suffix += 1
        username = f"{base_username}{suffix}"

    user = User(
        username=username,
        password=hash_password(secrets.token_urlsafe(32)),
        name=name or "",
        email=email_norm,
        role="member",
        status="active",
        works_user_id=works_user_id,
        auth_provider="works",
    )
    db.add(user)
    db.flush()
    link_user_to_employee(db, user)
    return user, True


async def process_callback(
    db: Session,
    *,
    code: str,
    settings: Settings | None = None,
) -> User:
    """NAVER WORKS callback 흐름 전체. 호출자가 db.commit() 책임.

    state 검증은 라우터에서 수행. 본 함수는 token 교환·UserInfo 조회·DB upsert 담당.
    """
    s = settings or get_settings()
    if not s.works_enabled:
        raise SSOError("WORKS_ENABLED=false")
    if not s.works_client_id or not s.works_client_secret:
        raise SSOError("WORKS 클라이언트 자격이 설정되지 않았습니다")

    tokens = await exchange_code(s, code)
    access_token = tokens.get("access_token", "")
    if not access_token:
        raise SSOError("access_token이 응답에 없습니다")

    info = await fetch_user_info(s, access_token)
    if not _domain_matches(info, s.works_domain_id):
        raise SSOError("회사 도메인이 아닌 계정은 사용할 수 없습니다")

    works_user_id = str(info.get("userId") or "")
    email = str(info.get("email") or "")
    name = _extract_name(info)
    if not works_user_id or not email:
        raise SSOError("NAVER WORKS 응답에 userId/email이 누락되었습니다")

    user, _created = upsert_user(
        db,
        works_user_id=works_user_id,
        email=email,
        name=name,
        blocked_emails=s.works_blocked_emails_set,
    )
    user.sso_login_at = datetime.now(UTC)
    return user
