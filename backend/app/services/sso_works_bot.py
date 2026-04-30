"""NAVER WORKS Bot — Service Account JWT 인증 + 메시지 전송.

NAVER WORKS Bot API는 admin OAuth(drive)와 별개로 Service Account JWT(RS256)를 받아
access_token을 발급한다. JWT는 Developer Console에서 받은 Private Key로 서명.

흐름:
1. JWT(RS256) 생성 — claim: iss=client_id, sub=service_account_id, exp=now+1h
2. POST /oauth2/v2.0/token (grant_type=jwt-bearer, assertion=JWT, scope=bot) → access_token
3. POST /v1.0/bots/{botId}/users/{userId}/messages — 사용자 1명에게 메시지

토큰은 모듈 메모리에 캐시 (만료 60초 전 refresh, 단일 lock으로 중복 발급 방지).
실패는 절대 호출자 트랜잭션을 막지 않음 — caller가 fire-and-forget 패턴으로 호출하면 됨.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from jose import jwt as jose_jwt

from app.settings import Settings, get_settings

logger = logging.getLogger("sso.works_bot")

_TOKEN_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/token"
_BOT_API_BASE = "https://www.worksapis.com/v1.0"
_HTTP_TIMEOUT = 15.0

_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}
_token_lock = asyncio.Lock()


def _normalize_private_key(raw: str) -> str:
    """env에 single-line으로 들어간 PEM의 `\\n` 이스케이프를 실제 줄바꿈으로 복원.

    Render·dotenv 모두 multiline 지원하지만 운영자가 single-line으로 붙여넣는 경우가
    잦아 호환 처리.
    """
    if "\\n" in raw and "\n" not in raw:
        return raw.replace("\\n", "\n")
    return raw


async def _get_access_token() -> str:
    s = get_settings()
    async with _token_lock:
        now = time.time()
        if _token_cache["value"] and _token_cache["expires_at"] > now + 60:
            return str(_token_cache["value"])
        iat = int(now)
        claim = {
            "iss": s.works_client_id,
            "sub": s.works_bot_service_account_id,
            "iat": iat,
            "exp": iat + 3600,
        }
        private_key = _normalize_private_key(s.works_bot_private_key)
        try:
            assertion = jose_jwt.encode(claim, private_key, algorithm="RS256")
        except Exception as e:
            raise RuntimeError(f"Bot JWT 서명 실패 — Private Key 형식 확인 필요: {e}") from e
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as cli:
            r = await cli.post(
                _TOKEN_ENDPOINT,
                data={
                    "assertion": assertion,
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "client_id": s.works_client_id,
                    "client_secret": s.works_client_secret,
                    "scope": "bot",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if r.status_code != 200:
            raise RuntimeError(
                f"Bot 토큰 발급 실패 ({r.status_code}): {r.text[:300]}"
            )
        body = r.json()
        token = str(body.get("access_token") or "")
        if not token:
            raise RuntimeError("Bot 토큰 응답에 access_token 없음")
        expires_in = int(body.get("expires_in", 3600) or 3600)
        _token_cache["value"] = token
        _token_cache["expires_at"] = now + max(60, expires_in)
        return token


async def send_text(user_id: str, text: str) -> bool:
    """user_id(이메일 또는 GUID)에게 텍스트 메시지. 실패 시 warn 로그만 + False 반환.

    호출자는 결과 무시 가능 (fire-and-forget). enabled=false 또는 user_id 빈 값이면
    skip + False.
    """
    s = get_settings()
    if not s.works_bot_enabled:
        return False
    if not s.works_bot_id:
        logger.warning("WORKS_BOT_ID 미설정 — 메시지 skip")
        return False
    if not user_id:
        logger.debug("Bot send_text: user_id 빈 값 — skip")
        return False
    text = (text or "").strip()
    if not text:
        return False
    try:
        token = await _get_access_token()
    except Exception as e:
        logger.warning("Bot 토큰 발급 실패: %s", e)
        return False
    url = f"{_BOT_API_BASE}/bots/{s.works_bot_id}/users/{user_id}/messages"
    body = {"content": {"type": "text", "text": text}}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as cli:
            r = await cli.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
    except httpx.HTTPError as e:
        logger.warning("Bot send_text 네트워크 오류: %s", e)
        return False
    if r.status_code >= 400:
        logger.warning(
            "Bot send_text 실패 %s %s: %s",
            r.status_code,
            user_id,
            r.text[:300],
        )
        return False
    return True


def reset_token_cache_for_test() -> None:
    """테스트용 — module-level cache를 초기화."""
    _token_cache["value"] = ""
    _token_cache["expires_at"] = 0.0
