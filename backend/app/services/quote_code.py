"""견적서 문서번호 자동 부여 — {YY}-{CC}-{NNN} 형식.

영업코드(`영{YY}-{NNN}`)와 별개로, 견적서마다 연 단위 sequence로 부여.
사장 운영 양식의 "26-01-007"(구조설계) "26-04-002"(정기점검) 등 형식 유지.

매핑 정책:
- YY: 견적 작성일(KST) 연도 2자리
- CC: 견적서 종류 분류 코드 (`_CODE_MAP` 참조)
- NNN: (해당 연도, 분류) 내 max(번호) + 1, 3자리 zero-padded
- PostgreSQL advisory_xact_lock으로 동시성 보호 ((연도, 분류)별 lock key)
- 사장 노션 DB의 수동 입력 row도 mirror_sales sync 후 max 탐색 대상에 포함됨

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
from app.services.quote_calculator import QuoteType

_KST = timezone(timedelta(hours=9))
_DOC_RE = re.compile(r"^(\d{2})-(\d{2})-(\d+)$")

# 견적서 종류별 분류 코드 — 사장 운영 파일명 패턴에서 reverse-engineering.
# 운영 코드와 다르면 한 번에 수정.
_CODE_MAP: dict[QuoteType, str] = {
    QuoteType.STRUCT_DESIGN: "01",
    QuoteType.STRUCT_REVIEW: "02",
    QuoteType.PERF_SEISMIC: "03",
    QuoteType.INSPECTION_REGULAR: "04",
    QuoteType.INSPECTION_DETAIL: "05",
    QuoteType.INSPECTION_DIAGNOSIS: "06",
    QuoteType.INSPECTION_BMA: "07",
    QuoteType.SEISMIC_EVAL: "08",
    QuoteType.SUPERVISION: "09",
    QuoteType.FIELD_SUPPORT: "10",
    # 내진평가 패키지 부속 모듈 — α 패턴 (별 영업 + 통합 PDF)
    QuoteType.REINFORCEMENT_DESIGN: "11",
    QuoteType.THIRD_PARTY_REVIEW: "12",
    QuoteType.CUSTOM: "99",
}


def _resolve_quote_type(value: str | QuoteType | None) -> QuoteType:
    """문자열/None을 QuoteType으로 정규화. 빈 값은 STRUCT_DESIGN."""
    if isinstance(value, QuoteType):
        return value
    if not value:
        return QuoteType.STRUCT_DESIGN
    try:
        return QuoteType(value)
    except ValueError:
        return QuoteType.STRUCT_DESIGN


def _advisory_lock_key(year_yy: int, category_code: str) -> int:
    """(연도, 분류 코드)별 advisory lock key. sales_code base와 충돌하지 않도록.

    "QDC\\0..." prefix + (YY*100 + 분류 정수)
    """
    return 0x5144430000000000 + year_yy * 100 + int(category_code)


def next_quote_doc_number(
    db: Session, quote_type: str | QuoteType | None = None
) -> str:
    """다음 {YY}-{CC}-{NNN} 문서번호 발급. advisory lock 보호.

    quote_type 빈 값/None이면 구조설계('01') 분류로 발급.
    호출자 책임: 동일 트랜잭션에서 발급 + INSERT를 마쳐야 lock이 의미 있음.
    트랜잭션 종료 시 lock 자동 해제.
    """
    qtype = _resolve_quote_type(quote_type)
    category_code = _CODE_MAP[qtype]
    year_yy = datetime.now(_KST).year % 100
    prefix = f"{year_yy:02d}-{category_code}-"

    db.execute(
        text("SELECT pg_advisory_xact_lock(:k)"),
        {"k": _advisory_lock_key(year_yy, category_code)},
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
        if int(m.group(1)) != year_yy or m.group(2) != category_code:
            continue
        try:
            n = int(m.group(3))
            if n > max_n:
                max_n = n
        except ValueError:
            continue
    return f"{prefix}{max_n + 1:03d}"
