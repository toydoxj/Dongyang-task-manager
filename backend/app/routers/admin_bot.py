"""/api/admin/bot — NAVER WORKS Bot 동작 검증용 admin 엔드포인트.

setup 직후 admin이 본인에게 테스트 메시지를 보내 다음 항목을 검증:
- Service Account JWT(RS256) 서명 OK
- Client ID/Secret + Service Account ID로 access_token 발급 OK
- Bot ID + 사용자 ID로 메시지 송신 OK

실패 시 trace를 응답으로 노출해 setup 디버깅 시간을 단축한다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.employee import Employee
from app.security import require_admin
from app.services import sso_works_bot
from app.settings import get_settings

logger = logging.getLogger("admin.bot")
router = APIRouter(prefix="/admin/bot", tags=["admin-bot"])


class PemDiagnostic(BaseModel):
    """PEM 입력 상태 — secret 본문은 노출하지 않고 구조 metadata만."""

    raw_length: int = 0
    raw_lines: int = 0
    raw_has_escape: bool = False           # `\n` 이스케이프 존재
    raw_has_real_newline: bool = False     # 실제 LF 존재
    raw_has_cr: bool = False               # CR (Windows 줄바꿈 잔존)
    raw_first_40: str = ""
    raw_last_40: str = ""
    normalized_length: int = 0
    normalized_lines: int = 0
    normalized_first_40: str = ""
    normalized_last_40: str = ""
    has_begin_marker: bool = False
    has_end_marker: bool = False


class BotTestResponse(BaseModel):
    ok: bool
    enabled: bool
    bot_id: str = ""
    target_user_id: str = ""
    error: str = ""
    pem_diag: PemDiagnostic | None = None


def _pem_diag(raw: str) -> PemDiagnostic:
    normalized = sso_works_bot._normalize_private_key(raw)
    return PemDiagnostic(
        raw_length=len(raw),
        raw_lines=raw.count("\n") + 1 if raw else 0,
        raw_has_escape="\\n" in raw,
        raw_has_real_newline="\n" in raw,
        raw_has_cr="\r" in raw,
        raw_first_40=raw[:40],
        raw_last_40=raw[-40:] if len(raw) > 40 else raw,
        normalized_length=len(normalized),
        normalized_lines=normalized.count("\n") + 1 if normalized else 0,
        normalized_first_40=normalized[:40],
        normalized_last_40=normalized[-40:] if len(normalized) > 40 else normalized,
        has_begin_marker="-----BEGIN" in normalized,
        has_end_marker="-----END" in normalized,
    )


@router.post("/test-message", response_model=BotTestResponse)
async def send_test_message(
    to: str | None = None,
    diag: bool = False,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BotTestResponse:
    """admin 본인 또는 지정 대상에게 테스트 메시지 발송.

    `to` 파라미터:
        - 비우면 admin 본인의 works_user_id 또는 email로 발송
        - 이메일 또는 NAVER WORKS userId 직접 입력 가능
        - 또는 Employee 테이블의 직원 이름 — 그 직원의 works_user_id/email로 fallback
    """
    s = get_settings()
    if not s.works_bot_enabled:
        return BotTestResponse(
            ok=False,
            enabled=False,
            error=(
                "WORKS_BOT_ENABLED=false. Render Environment에 true로 설정 필요."
            ),
        )
    missing = [
        k
        for k, v in {
            "WORKS_BOT_ID": s.works_bot_id,
            "WORKS_BOT_SERVICE_ACCOUNT_ID": s.works_bot_service_account_id,
            "WORKS_BOT_PRIVATE_KEY": s.works_bot_private_key,
            "WORKS_CLIENT_ID": s.works_client_id,
            "WORKS_CLIENT_SECRET": s.works_client_secret,
        }.items()
        if not v
    ]
    if missing:
        return BotTestResponse(
            ok=False,
            enabled=True,
            bot_id=s.works_bot_id,
            error=f"환경변수 누락: {', '.join(missing)}",
        )

    target = (to or "").strip()
    if not target:
        target = (user.works_user_id or "") or (user.email or "")
    elif "@" not in target and target:
        # 이름으로 들어온 경우 Employee에서 lookup
        from sqlalchemy import select

        emp = db.execute(
            select(Employee).where(Employee.name == target)
        ).scalar_one_or_none()
        if emp:
            target = (emp.works_user_id or "") or (emp.email or "")

    if not target:
        return BotTestResponse(
            ok=False,
            enabled=True,
            bot_id=s.works_bot_id,
            error="수신자 식별 실패 — admin 본인의 email/works_user_id가 비어있거나 to 파라미터가 잘못됨",
        )

    text = (
        "🔔 [Bot 동작 테스트]\n"
        f"발신: {user.name or user.username}\n"
        "이 메시지가 보이면 setup이 정상입니다."
    )

    # 직접 호출(fire-and-forget 아님) — 동기 결과로 OK/실패 즉시 응답
    try:
        # send_text는 내부적으로 token 발급 → POST 메시지 → True/False 반환
        ok = await sso_works_bot.send_text(target, text)
    except Exception as e:  # noqa: BLE001
        logger.exception("Bot 테스트 메시지 전송 중 예외")
        raise HTTPException(status_code=500, detail=f"전송 중 예외: {e}") from e

    pem_diag = _pem_diag(s.works_bot_private_key) if (diag or not ok) else None

    return BotTestResponse(
        ok=ok,
        enabled=True,
        bot_id=s.works_bot_id,
        target_user_id=target,
        error=(
            ""
            if ok
            else "send_text False — backend Logs에서 'Bot send_text 실패' 또는 토큰 오류 확인"
        ),
        pem_diag=pem_diag,
    )
