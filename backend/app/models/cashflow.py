"""수금/지출 통합 시계열 DTO."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app.services import notion_props as P

EntryType = Literal["income", "expense"]


class CashflowEntry(BaseModel):
    id: str
    type: EntryType
    date: str | None  # ISO YYYY-MM-DD
    amount: float
    category: str = ""        # 수금: 회차 표시, 지출: 구분
    project_ids: list[str] = []
    note: str = ""
    # 수금(income)에만 사용 — 노션 "실지급" relation. 발주처 DB와 동일 DB.
    # 등록되지 않은 경우 page_id 없이 비어 있을 수 있음.
    round_no: int | None = None
    payer_relation_ids: list[str] = []
    payer_names: list[str] = []  # 라우터에서 발주처 mirror로 해결
    # 공동수급/추가용역 — 매칭된 분담 항목(노션 contract_items DB) page_id.
    # 노션 컬럼명은 "계약항목" relation. 이 row가 어느 분담분에 차감되는지 결정.
    contract_item_id: str | None = None
    contract_item_label: str | None = None  # 라우터에서 mirror_contract_items로 해결

    @classmethod
    def from_income_page(cls, page: dict[str, Any]) -> "CashflowEntry":
        props = page.get("properties", {})
        round_no = P.number(props, "회차")
        ci_ids = P.relation_ids(props, "계약항목")
        return cls(
            id=page.get("id", ""),
            type="income",
            date=P.date_range(props, "수금일")[0],
            amount=P.number(props, "수금액(원)") or 0.0,
            category=f"{int(round_no)}회차" if round_no else "",
            round_no=int(round_no) if round_no else None,
            project_ids=P.relation_ids(props, "(주)동양구조 업무관리 - 프로젝트"),
            payer_relation_ids=P.relation_ids(props, "실지급"),
            contract_item_id=ci_ids[0] if ci_ids else None,
            note=P.rich_text(props, "비고"),
        )

    @classmethod
    def from_expense_page(cls, page: dict[str, Any]) -> "CashflowEntry":
        props = page.get("properties", {})
        return cls(
            id=page.get("id", ""),
            type="expense",
            date=P.date_range(props, "지출일")[0],
            amount=P.number(props, "금액") or 0.0,
            category=P.select_name(props, "구분"),
            project_ids=P.relation_ids(props, "프로젝트"),
            note=P.rich_text(props, "메모"),
        )


class CashflowResponse(BaseModel):
    items: list[CashflowEntry]
    income_total: float
    expense_total: float
    net: float
    count: int
