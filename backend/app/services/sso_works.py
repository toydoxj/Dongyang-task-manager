"""NAVER WORKS OIDC SSO — Phase 1.

- OIDC discovery, authorize URL builder, code → token exchange
- id_token RS256 + JWKS 검증 + iss/aud/exp/nonce/email/domain 검증
- DB upsert (works_user_id 우선, 이메일 fallback, 신규는 자동 active+member)

키 회전 대비: JWKS 검증 실패 시 1회 force refetch.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import jwt
from sqlalchemy.orm import Session

from app.models.auth import User
from app.security import hash_password
from app.services.employee_link import link_user_to_employee
from app.settings import Settings, get_settings

logger = logging.getLogger("sso.works")

ALLOWED_EMAIL_DOMAIN = "@dyce.kr"

_DISCOVERY_TTL_S = 24 * 3600
_JWKS_TTL_S = 3600
_DISCOVERY_PATH = "/.well-known/openid-configuration"


class SSOError(Exception):
    """SSO 흐름 중 사용자에게 노출 가능한 에러."""


class _JWKSKidNotFound(SSOError):
    """id_token의 kid가 캐시된 JWKS에 없음 → 키 회전 가능성, force refetch 트리거."""


class _Cache:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._discovery: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None

    async def get_discovery(self, settings: Settings) -> dict[str, Any]:
        async with self._lock:
            now = time.monotonic()
            if self._discovery and now - self._discovery[0] < _DISCOVERY_TTL_S:
                return self._discovery[1]
        url = f"{settings.works_issuer.rstrip('/')}{_DISCOVERY_PATH}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        async with self._lock:
            self._discovery = (time.monotonic(), data)
        return data

    async def get_jwks(
        self, settings: Settings, *, force: bool = False
    ) -> dict[str, Any]:
        async with self._lock:
            now = time.monotonic()
            if not force and self._jwks and now - self._jwks[0] < _JWKS_TTL_S:
                return self._jwks[1]
        disco = await self.get_discovery(settings)
        url = disco.get("jwks_uri")
        if not url:
            raise SSOError("OIDC discovery에 jwks_uri가 없습니다")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        async with self._lock:
            self._jwks = (time.monotonic(), data)
        return data


_cache = _Cache()


def make_state_and_nonce() -> tuple[str, str]:
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)


async def authorize_url(settings: Settings, state: str, nonce: str) -> str:
    disco = await _cache.get_discovery(settings)
    auth_endpoint = disco.get("authorization_endpoint", "")
    if not auth_endpoint:
        raise SSOError("OIDC discovery에 authorization_endpoint가 없습니다")
    params = {
        "response_type": "code",
        "client_id": settings.works_client_id,
        "redirect_uri": settings.works_redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    return f"{auth_endpoint}?{urlencode(params)}"


async def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    disco = await _cache.get_discovery(settings)
    token_endpoint = disco.get("token_endpoint", "")
    if not token_endpoint:
        raise SSOError("OIDC discovery에 token_endpoint가 없습니다")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.works_redirect_uri,
        "client_id": settings.works_client_id,
        "client_secret": settings.works_client_secret,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_endpoint,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            logger.warning(
                "token endpoint failed: %s %s", resp.status_code, resp.text
            )
            raise SSOError("토큰 교환에 실패했습니다")
        return resp.json()


async def verify_id_token(
    settings: Settings, id_token: str, expected_nonce: str
) -> dict[str, Any]:
    """RS256 + JWKS + iss/aud/exp/nonce 검증."""
    headers = jwt.get_unverified_header(id_token)
    kid = headers.get("kid", "")
    alg = headers.get("alg", "")
    if alg != "RS256":
        raise SSOError(f"지원하지 않는 알고리즘: {alg}")

    async def _try(force: bool) -> dict[str, Any]:
        jwks_data = await _cache.get_jwks(settings, force=force)
        keys = jwks_data.get("keys", [])
        match = next((k for k in keys if k.get("kid") == kid), None)
        if match is None:
            raise _JWKSKidNotFound("JWKS에서 일치하는 키를 찾지 못했습니다")
        # at_hash는 Authorization Code Flow + 별도 access_token에 한해 의미가 있고,
        # NAVER WORKS는 id_token만으로 식별 흐름이라 검증 생략.
        return jwt.decode(
            id_token,
            match,
            algorithms=["RS256"],
            audience=settings.works_client_id,
            issuer=settings.works_issuer,
            options={"verify_at_hash": False},
        )

    # 키 회전(kid 불일치)일 때만 force refetch — 서명 실패/만료 등 검증 오류는 즉시 raise.
    # (유효하지 않은 토큰을 반복 전송해 JWKS 엔드포인트를 폭주시키는 amplification 회피)
    try:
        claims = await _try(force=False)
    except _JWKSKidNotFound:
        claims = await _try(force=True)

    if claims.get("nonce") != expected_nonce:
        raise SSOError("nonce 불일치")
    return claims


def _domain_matches(claims: dict[str, Any], expected: str) -> bool:
    """NAVER WORKS id_token의 domain claim 검증.

    표기가 'domain', 'domain_id', 'domainId' 중 하나로 올 수 있어 셋 다 허용.
    """
    if not expected:
        return True  # 미설정 시 검증 생략 (개발/스테이징 편의)
    for key in ("domain_id", "domain", "domainId"):
        v = claims.get(key)
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
) -> tuple[User, bool]:
    """works_user_id 우선, email fallback. 신규는 자동 active+member.

    호출자가 db.commit() 책임. 반환 (user, created).
    """
    email_norm = (email or "").strip().lower()
    if not email_norm.endswith(ALLOWED_EMAIL_DOMAIN):
        raise SSOError(
            f"이메일은 회사 계정({ALLOWED_EMAIL_DOMAIN})만 사용 가능합니다"
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
    expected_nonce: str,
    settings: Settings | None = None,
) -> User:
    """NAVER WORKS callback 흐름 전체. 호출자가 db.commit() 책임."""
    s = settings or get_settings()
    if not s.works_enabled:
        raise SSOError("WORKS_ENABLED=false")
    if not s.works_client_id or not s.works_client_secret:
        raise SSOError("WORKS 클라이언트 자격이 설정되지 않았습니다")

    tokens = await exchange_code(s, code)
    id_token = tokens.get("id_token", "")
    if not id_token:
        raise SSOError("id_token이 응답에 없습니다")

    claims = await verify_id_token(s, id_token, expected_nonce)
    if not _domain_matches(claims, s.works_domain_id):
        raise SSOError("회사 도메인이 아닌 계정은 사용할 수 없습니다")

    sub = str(claims.get("sub", ""))
    email = str(claims.get("email", ""))
    name = str(claims.get("name") or claims.get("preferred_username") or "")
    if not sub or not email:
        raise SSOError("필수 클레임(sub/email)이 누락되었습니다")

    user, _created = upsert_user(db, works_user_id=sub, email=email, name=name)
    user.sso_login_at = datetime.now(UTC)
    return user
