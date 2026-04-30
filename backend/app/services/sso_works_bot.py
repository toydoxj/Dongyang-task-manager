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
import re
import time
from typing import Any

import httpx
from jose import jwt as jose_jwt

from app.settings import Settings, get_settings

logger = logging.getLogger("sso.works_bot")

_PEM_RE = re.compile(
    r"^(?P<header>-----BEGIN [A-Z ]+-----)(?P<body>.+?)(?P<footer>-----END [A-Z ]+-----)\s*$",
    re.DOTALL,
)

_TOKEN_ENDPOINT = "https://auth.worksmobile.com/oauth2/v2.0/token"
_BOT_API_BASE = "https://www.worksapis.com/v1.0"
_HTTP_TIMEOUT = 15.0

_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}
_token_lock = asyncio.Lock()


_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=]+$")


def _normalize_private_key(raw: str) -> str:
    """다양한 형태로 들어온 PEM을 cryptography가 받아들이는 표준 형태로 복원.

    Render env / dotenv의 multi-line 지원 한계 때문에 운영자가 다음 중 한 가지로
    PEM을 입력하는 경우가 잦다 — 모두 같은 표준 PEM으로 정규화한다:

    1) 정상 multi-line — 줄마다 base64 64자 + LF, BEGIN/END 마커 양 끝
    2) `\\n` 이스케이프 single-line — `-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END...`
    3) 공백 평탄화 single-line — `-----BEGIN PRIVATE KEY----- MIIE Awg... -----END...`
       (paste 과정에서 multi-line이 공백/탭으로 squash된 경우)
    4) BEGIN/END 마커 누락 — base64 본문만 들어옴. PKCS#8 PRIVATE KEY로 가정하고
       마커 자동 추가 (NAVER WORKS Service Account 키는 PKCS#8 표준).

    cryptography의 `MalformedFraming` 에러는 (3)/(4) 형태에서 발생한다.
    """
    raw = (raw or "").strip()
    if not raw:
        return raw
    # (2) 명시적 이스케이프 — 줄바꿈이 진짜 없는 경우만
    if "\\n" in raw and "\n" not in raw:
        raw = raw.replace("\\n", "\n")

    has_begin = "-----BEGIN" in raw
    has_end = "-----END" in raw

    # (4) 마커 누락 — base64만 있다고 가정하고 PKCS#8 PRIVATE KEY로 wrapping
    if not has_begin and not has_end:
        body = re.sub(r"\s+", "", raw)
        if _BASE64_RE.match(body):
            wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
            return (
                "-----BEGIN PRIVATE KEY-----\n"
                f"{wrapped}\n"
                "-----END PRIVATE KEY-----\n"
            )
        return raw  # base64도 아니면 그대로 — cryptography가 명확한 에러를 띄우게

    # (1) 마커 + multi-line 정상 → trailing newline만 보장
    if "\n" in raw:
        return raw + ("\n" if not raw.endswith("\n") else "")

    # (3) 마커 + single-line 평탄화 — 본문을 64자 wrap
    m = _PEM_RE.match(raw)
    if not m:
        return raw
    header = m.group("header").strip()
    body = re.sub(r"\s+", "", m.group("body"))
    footer = m.group("footer").strip()
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"{header}\n{wrapped}\n{footer}\n"


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
