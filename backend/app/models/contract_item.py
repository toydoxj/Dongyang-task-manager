"""프로젝트 계약 항목 (공동수급·추가 용역) DTO.

한 프로젝트에 여러 (발주처, 금액, 라벨) 항목을 둔다. 노션 별도 sub-DB
"프로젝트 계약 항목"의 페이지 1건이 1 ContractItem.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services import notion_props as P


class ContractItem(BaseModel):
    id: str
    project_id: str  # 프로젝트 page_id (relation 단일)
    client_id: str  # 발주처 page_id (relation 단일)
    client_name: str = ""  # 라우터에서 mirror로 해결
    label: str = ""
    amount: float = 0
    vat: float = 0
    sort_order: int = 0

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "ContractItem":
        props = page.get("properties", {})
        project_ids = P.relation_ids(props, "프로젝트")
        client_ids = P.relation_ids(props, "발주처")
        return cls(
            id=page.get("id", ""),
            project_id=project_ids[0] if project_ids else "",
            client_id=client_ids[0] if client_ids else "",
            label=P.title(props, "라벨"),
            amount=P.number(props, "금액") or 0.0,
            vat=P.number(props, "VAT") or 0.0,
            sort_order=int(P.number(props, "정렬") or 0),
        )


class ContractItemListResponse(BaseModel):
    items: list[ContractItem]
    count: int


class ContractItemCreateRequest(BaseModel):
    project_id: str
    client_id: str
    label: str = "본 계약"
    amount: float = 0
    vat: float = 0
    sort_order: int = 0


class ContractItemUpdateRequest(BaseModel):
    """None 필드는 변경 안 함."""

    project_id: str | None = None
    client_id: str | None = None
    label: str | None = None
    amount: float | None = None
    vat: float | None = None
    sort_order: int | None = None


def contract_item_create_props(req: ContractItemCreateRequest) -> dict[str, Any]:
    return {
        "라벨": {"title": [{"text": {"content": req.label or "본 계약"}}]},
        "프로젝트": {"relation": [{"id": req.project_id}]},
        "발주처": {"relation": [{"id": req.client_id}]},
        "금액": {"number": req.amount},
        "VAT": {"number": req.vat},
        "정렬": {"number": req.sort_order},
    }


def contract_item_update_props(req: ContractItemUpdateRequest) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if req.label is not None:
        props["라벨"] = {"title": [{"text": {"content": req.label}}]}
    if req.project_id is not None:
        props["프로젝트"] = {"relation": [{"id": req.project_id}]}
    if req.client_id is not None:
        props["발주처"] = {"relation": [{"id": req.client_id}]}
    if req.amount is not None:
        props["금액"] = {"number": req.amount}
    if req.vat is not None:
        props["VAT"] = {"number": req.vat}
    if req.sort_order is not None:
        props["정렬"] = {"number": req.sort_order}
    return props
