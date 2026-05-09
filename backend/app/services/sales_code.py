"""영업 CODE 자동 부여 — `영{YY}-{NNN}` 형식 (신).

연도별로 sequence를 관리. 동시 생성 시 race condition을 방지하기 위해
PostgreSQL advisory lock(년도 별 hash)을 사용한다.

매핑 정책:
- 연도(YY): 영업 등록일(KST 기준) 2자리. 26-01-01에 등록하면 영26-001
- 순번(NNN): 해당 연도 내 영업 건의 max(번호) + 1, 3자리 zero-padded
- 노션에서 수동 수정도 허용 — 자동 부여 후 PM이 노션에서 변경하면 다음 sync에 그대로 반영
- 옛 형식 `{YY}-영업-{NNN}`도 sequence pool에 포함 — 연속성 유지 (예: 옛 158 다음 신 영26-159)

운영 부담:
- 영업 등록은 일 단위로도 한 자릿수 빈도이므로 advisory lock의 충돌 비용은 무시 가능
- mirror_sales 데이터 손실 시(예: DB 복구) 다음 부여가 옛 번호와 충돌할 수 있음 — 그 경우 PM이 수동 보정
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models import mirror as M

_KST = timezone(timedelta(hours=9))
# 신 형식: 영{YY}-{NNN} / 옛 형식: {YY}-영업-{NNN}. 둘 모두 sequence pool 포함.
_CODE_RE_NEW = re.compile(r"^영(\d{2})-(\d+)$")
_CODE_RE_OLD = re.compile(r"^(\d{2})-영업-(\d+)$")


def _kst_year_yy() -> int:
    """현재 KST 연도의 마지막 2자리 (예: 2026 → 26)."""
    return datetime.now(_KST).year % 100


def _advisory_lock_key(year_yy: int) -> int:
    """연도별 advisory lock key. 연도 2자리에 base를 더해 고유 키 생성."""
    # PostgreSQL advisory lock은 bigint key. 충돌 위험 최소화 위해 임의 base.
    return 0x534C5300_00000000 + year_yy  # "SLS\0..."


def next_sales_code(db: Session, year_yy: int | None = None) -> str:
    """다음 `영{YY}-{NNN}` CODE 발급. advisory lock 보호.

    호출자 책임: 동일 트랜잭션에서 발급 + INSERT를 마쳐야 lock이 의미 있음.
    트랜잭션 종료 시 lock 자동 해제.
    """
    yy = year_yy if year_yy is not None else _kst_year_yy()
    new_prefix = f"영{yy:02d}-"
    old_prefix = f"{yy:02d}-영업-"

    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _advisory_lock_key(yy)},
    )

    stmt = select(M.MirrorSales.code).where(
        or_(
            M.MirrorSales.code.like(f"{new_prefix}%"),
            M.MirrorSales.code.like(f"{old_prefix}%"),
        )
    )
    rows = db.execute(stmt).all()
    max_n = 0
    for (code,) in rows:
        m = _CODE_RE_NEW.match(code or "") or _CODE_RE_OLD.match(code or "")
        if not m:
            continue
        if int(m.group(1)) != yy:
            continue
        try:
            n = int(m.group(2))
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{new_prefix}{max_n + 1:03d}"
