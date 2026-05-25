"""mirror ORM row → 도메인 DTO 변환.

properties JSONB가 노션 raw 그대로 저장돼 있어서 기존 from_notion_page를 그대로 재사용한다.
"""
from __future__ import annotations

from datetime import datetime

from app.models import mirror as M
from app.models.cashflow import CashflowEntry
from app.models.contract_item import ContractItem
from app.models.project import Project
from app.models.sale import Sale
from app.models.task import Task


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _as_page(
    *, page_id: str, properties: dict, url: str, last_edited_time: datetime | None
) -> dict:
    return {
        "id": page_id,
        "properties": properties or {},
        "url": url or None,
        "last_edited_time": _iso(last_edited_time),
    }


def project_from_mirror(row: M.MirrorProject) -> Project:
    return Project.from_notion_page(
        _as_page(
            page_id=row.page_id,
            properties=row.properties,
            url=row.url,
            last_edited_time=row.last_edited_time,
        )
    )


def task_from_mirror(row: M.MirrorTask) -> Task:
    return Task.from_notion_page(
        _as_page(
            page_id=row.page_id,
            properties=row.properties,
            url=row.url,
            last_edited_time=row.last_edited_time,
        )
    )


def sale_from_mirror(row: M.MirrorSales) -> Sale:
    """mirror row → Sale.

    PR-FU (2026-05-25): 정규화 컬럼 우선, properties fallback.
    옛 PR-FT 회귀 — properties dict에 "견적서명"/"영업코드" 키 누락된 row가 있으면
    Sale.from_notion_page가 빈 값 반환 → 모달 prefill 빈 string → 사용자 저장 시
    빈 값으로 PATCH → mirror 영구 손실 cascade.
    정규화 컬럼(row.code/name)은 sync._upsert_sale_inner가 추출해 저장한 신뢰값.
    """
    sale = Sale.from_notion_page(
        _as_page(
            page_id=row.page_id,
            properties=row.properties,
            url=row.url,
            last_edited_time=row.last_edited_time,
        )
    )
    # 정규화 컬럼 우선 (mirror.code/name이 빈 값일 때만 properties 결과 사용)
    if row.code:
        sale.code = row.code
    if row.name:
        sale.name = row.name
    if row.kind:
        sale.kind = row.kind
    if row.stage:
        sale.stage = row.stage
    # quote_form_data는 노션에 저장하지 않고 mirror_sales에만 보관 — 응답에 직접 주입
    sale.quote_form_data = row.quote_form_data or {}
    return sale


def cashflow_from_mirror(row: M.MirrorCashflow) -> CashflowEntry:
    page = {"id": row.page_id, "properties": row.properties or {}}
    if row.kind == "income":
        return CashflowEntry.from_income_page(page)
    return CashflowEntry.from_expense_page(page)


def contract_item_from_mirror(row: M.MirrorContractItem) -> ContractItem:
    """직접 컬럼 우선 사용 — properties JSON parse를 한 번 더 돌리지 않음."""
    return ContractItem(
        id=row.page_id,
        project_id=row.project_id or "",
        client_id=row.client_id or "",
        label=row.label or "",
        amount=float(row.amount or 0),
        vat=float(row.vat or 0),
        sort_order=int(row.sort_order or 0),
    )
