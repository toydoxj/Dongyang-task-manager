"""견적서 문서번호 자동 부여 — {YY}-01-{NNN} 형식.

영업코드(`{YY}-영업-{NNN}`)와 별개로, 견적서마다 연 단위 sequence로 부여.
사장 운영 양식의 "26-01-007" 형식 유지.

매핑 정책:
- YY: 견적 작성일(KST) 연도 2자리
- 01: 분류 코드. 구조설계는 항상 '01' (사장 운영 표준). 향후 다른 분류
  추가 시 인자로 확장
- NNN: 해당 연 내 견적의 max(번호) + 1, 3자리 zero-padded
- PostgreSQL advisory_xact_lock으로 동시성 보호 (연별 lock key)
- 사장 노션 DB의 수동 입력 row(26-01-NNN)도 mirror_sales sync 후 max
  탐색 대상에 포함됨 — 자동/수동 번호 충돌 방지

운영 부담:
- 견적서 작성은 일별 1~5건 수준 → advisory lock 충돌 비용 무시 가능
- mirror_sales 데이터 손실 시(예: DB 복구) 다음 부여가 옛 번호와 충돌할 수
  있음 — 그 경우 PM이 노션에서 수동 보정
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import mirror as M

_KST = timezone(timedelta(hours=9))
_DOC_RE = re.compile(r"^(\d{2})-(\d{2})-(\d+)$")
_CATEGORY_CODE = "01"  # 구조설계


def _advisory_lock_key(year_yy: int) -> int:
    """연별 advisory lock key. sales_code의 base와 충돌하지 않도록 다른 prefix."""
    # "QDC\0..." prefix + YY
    return 0x5144430000000000 + year_yy


def next_quote_doc_number(db: Session) -> str:
    """다음 {YY}-01-{NNN} 문서번호 발급. advisory lock 보호.

    호출자 책임: 동일 트랜잭션에서 발급 + INSERT를 마쳐야 lock이 의미 있음.
    트랜잭션 종료 시 lock 자동 해제.
    """
    year_yy = datetime.now(_KST).year % 100
    prefix = f"{year_yy:02d}-{_CATEGORY_CODE}-"

    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _advisory_lock_key(year_yy)},
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
        if int(m.group(1)) != year_yy or m.group(2) != _CATEGORY_CODE:
            continue
        try:
            n = int(m.group(3))
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:03d}"
