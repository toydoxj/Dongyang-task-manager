"""영업(sales) aggregate.

PR-DK (Phase 4-J 21단계): weekly_report/__init__.py에서 분리.

| 함수 | 출력 | 의존 |
|---|---|---|
| `aggregate_sales` | `list[SalesItem]` | MirrorSales + `_client_name_lookup` / `_scale_text` (helpers) |

영업시작일(sales_start_date) 기반 cutoff. 종결 단계(수주확정/실주/취소/전환완료)
제외. helpers의 `_client_name_lookup`은 `mirror_clients`를 한 번만 fetch하는
dict — N+1 회피.

Model(`SalesItem`)은 `__init__.py`에 그대로 두고 import.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import mirror as M
from app.services.weekly_report import SalesItem
from app.services.weekly_report.helpers import _client_name_lookup, _scale_text


def aggregate_sales(
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[SalesItem]:
    """저번주 범위 내 시작된 영업 — 영업시작일(sales_start_date) 기준.

    종결 단계(수주확정/실주/취소/전환완료)는 제외. sales_start_date 비어있으면
    무시 (운영자가 노션에서 입력 안 한 영업).
    """
    rows = (
        db.query(M.MirrorSales)
        .filter(M.MirrorSales.archived.is_(False))
        .filter(~M.MirrorSales.stage.in_(["수주확정", "실주", "취소", "전환완료"]))
        .filter(M.MirrorSales.sales_start_date.isnot(None))
        .filter(M.MirrorSales.sales_start_date >= last_week_start)
        .filter(M.MirrorSales.sales_start_date <= last_week_end)
        .order_by(M.MirrorSales.code)
        .all()
    )
    client_name_by_id = _client_name_lookup(db)
    items: list[SalesItem] = []
    for s in rows:
        client_name = client_name_by_id.get(s.client_id, "") if s.client_id else ""
        items.append(
            SalesItem(
                page_id=s.page_id,
                code=s.code,
                category=list(s.category or []),
                name=s.name,
                client=client_name,
                scale=_scale_text(s),
                estimated_amount=s.estimated_amount,
                probability=s.probability,
                is_bid=s.is_bid,
                stage=s.stage,
                submission_date=s.submission_date.isoformat() if s.submission_date else None,
                sales_start_date=s.sales_start_date.isoformat() if s.sales_start_date else None,
            )
        )
    return items
