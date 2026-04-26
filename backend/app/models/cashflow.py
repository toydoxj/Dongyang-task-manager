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

    @classmethod
    def from_income_page(cls, page: dict[str, Any]) -> "CashflowEntry":
        props = page.get("properties", {})
        round_no = P.number(props, "회차")
        return cls(
            id=page.get("id", ""),
            type="income",
            date=P.date_range(props, "수금일")[0],
            amount=P.number(props, "수금액(원)") or 0.0,
            category=f"{int(round_no)}회차" if round_no else "",
            project_ids=P.relation_ids(props, "(주)동양구조 업무관리 - 프로젝트"),
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
