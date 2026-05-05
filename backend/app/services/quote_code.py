"""견적서 문서번호 자동 부여 — {YY}-{MM}-{NNN} 형식.

영업코드(`{YY}-영업-{NNN}`)와 별개로, 견적서마다 월별 sequence로 부여.
사장 운영 양식의 "26-01-007" 같은 형식 유지.

매핑 정책:
- YY: 견적 작성일(KST) 연도 2자리
- MM: 월 2자리
- NNN: 해당 월 내 견적의 max(번호) + 1, 3자리 zero-padded
- PostgreSQL advisory_xact_lock으로 동시성 보호 (월별 lock key)
- 노션 수동 수정 허용 — sync로 mirror 갱신, next_quote_doc_number는 mirror max를 봄

운영 부담:
- 견적서 작성은 일별 1~5건 수준 → advisory lock 충돌 비용 무시 가능
- mirror_sales 데이터 손실 시(예: DB 복구) 다음 부여가 옛 번호와 충돌할 수 있음 — 그 경우 PM이 수동 보정
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import mirror as M

_KST = timezone(timedelta(hours=9))
_DOC_RE = re.compile(r"^(\d{2})-(\d{2})-(\d+)$")


def _kst_year_month() -> tuple[int, int]:
    """현재 KST의 (YY, MM) 튜플."""
    now = datetime.now(_KST)
    return now.year % 100, now.month


def _advisory_lock_key(year_yy: int, month_mm: int) -> int:
    """연-월별 advisory lock key. sales_code의 base와 충돌하지 않도록 다른 prefix."""
    # "QDC\0..." prefix + (YY×100 + MM)
    return 0x5144430000000000 + year_yy * 100 + month_mm


def next_quote_doc_number(
    db: Session,
    year_yy: int | None = None,
    month_mm: int | None = None,
) -> str:
    """다음 {YY}-{MM}-{NNN} 문서번호 발급. advisory lock 보호.

    호출자 책임: 동일 트랜잭션에서 발급 + INSERT를 마쳐야 lock이 의미 있음.
    트랜잭션 종료 시 lock 자동 해제.
    """
    if year_yy is None or month_mm is None:
        yy, mm = _kst_year_month()
        year_yy = year_yy if year_yy is not None else yy
        month_mm = month_mm if month_mm is not None else mm
    prefix = f"{year_yy:02d}-{month_mm:02d}-"

    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _advisory_lock_key(year_yy, month_mm)},
    )

    stmt = select(M.MirrorSales.quote_doc_number).where(
        M.MirrorSales.quote_doc_number.like(f"{prefix}%")
    )
    rows = db.execute(stmt).all()
    max_n = 0
    for (doc,) in rows:
        m = _DOC_RE.match(doc or "")
        if not m:
            continue
        if int(m.group(1)) != year_yy or int(m.group(2)) != month_mm:
            continue
        try:
            n = int(m.group(3))
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:03d}"
