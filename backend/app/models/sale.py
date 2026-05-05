"""영업(Sales) DTO + 노션 properties 변환.

사장이 운영하던 '견적서 작성 리스트' DB의 페이지를 우리 앱이 사용할 형태로 변환.
수주영업(`kind=수주영업`)과 기술지원(`kind=기술지원`)을 단일 DTO에서 표현한다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services import notion_props as P


class Sale(BaseModel):
    """노션 영업 DB 페이지의 강타입 DTO."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str = ""           # 견적서명 (title)
    kind: str = ""           # 수주영업|기술지원
    stage: str = ""          # 견적준비|입찰대기|우선협상|낙찰|실주 (수주영업) 또는 기술지원 단계
    category: list[str] = []  # 업무내용 multi_select (구조검토/입찰설계/...)
    estimated_amount: float | None = None  # 견적금액 KRW
    is_bid: bool = False
    client_id: str = ""       # 의뢰처 relation 첫번째 (clients DB id)
    gross_floor_area: float | None = None  # 연면적 ㎡
    floors_above: float | None = None
    floors_below: float | None = None
    building_count: float | None = None
    note: str = ""
    submission_date: str | None = None
    vat_inclusive: str = ""   # 별도|포함
    performance_design_amount: float | None = None
    wind_tunnel_amount: float | None = None
    parent_lead_id: str = ""  # 상위 영업건 relation 첫번째 (self)
    converted_project_id: str = ""  # 전환된 프로젝트 relation 첫번째
    assignees: list[str] = []
    created_time: str | None = None
    last_edited_time: str | None = None
    url: str | None = None

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "Sale":
        props = page.get("properties", {})
        sub_start, _ = P.date_range(props, "제출일")
        return cls(
            id=page.get("id", ""),
            name=P.title(props, "견적서명"),
            kind=P.select_name(props, "유형"),
            stage=P.select_name(props, "단계"),
            category=P.multi_select_names(props, "업무내용"),
            estimated_amount=P.number(props, "견적금액"),
            is_bid=P.checkbox(props, "입찰여부"),
            client_id=_first_relation_id(props, "의뢰처"),
            gross_floor_area=P.number(props, "연면적"),
            floors_above=P.number(props, "지상층수"),
            floors_below=P.number(props, "지하층수"),
            building_count=P.number(props, "동수"),
            note=P.rich_text(props, "비고"),
            submission_date=sub_start,
            vat_inclusive=P.select_name(props, "VAT포함"),
            performance_design_amount=P.number(props, "성능설계"),
            wind_tunnel_amount=P.number(props, "풍동실험"),
            parent_lead_id=_first_relation_id(props, "상위 영업건"),
            converted_project_id=_first_relation_id(props, "전환된 프로젝트"),
            assignees=P.multi_select_names(props, "담당자"),
            created_time=page.get("created_time"),
            last_edited_time=page.get("last_edited_time"),
            url=page.get("url"),
        )


def _first_relation_id(props: dict[str, Any], name: str) -> str:
    """relation 컬럼에서 첫 비어있지 않은 id를 반환 — 빈 list나 빈 문자열 id 모두 안전 처리."""
    for rid in P.relation_ids(props, name):
        if rid:
            return rid
    return ""


class SaleListResponse(BaseModel):
    items: list[Sale]
    count: int
