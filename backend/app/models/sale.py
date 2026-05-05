"""영업(Sales) DTO + 노션 properties 변환.

사장이 운영하던 '견적서 작성 리스트' DB의 페이지를 우리 앱이 사용할 형태로 변환.
수주영업(`kind=수주영업`)과 기술지원(`kind=기술지원`)을 단일 DTO에서 표현한다.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field

from app.services import notion_props as P


class Sale(BaseModel):
    """노션 영업 DB 페이지의 강타입 DTO."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    code: str = ""           # 영업코드 {YY}-영업-{NNN}
    name: str = ""           # 견적서명 (title)
    kind: str = ""           # 수주영업|기술지원
    stage: str = ""          # 준비|진행|제출|완료|종결 (사장 5단계)
    category: list[str] = []  # 업무내용 multi_select (구조검토/입찰설계/...)
    estimated_amount: float | None = None  # 견적금액 KRW
    probability: float | None = None  # 수주확률 0~100 (PM 직접 입력)
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expected_revenue(self) -> float:
        """기대매출 = 견적금액 × (수주확률 / 100).

        견적금액·수주확률 어느 한쪽이 비어 있으면 0. PM이 노션 '수주확률' number
        컬럼에 0~100 직접 입력. 단계별 자동 확률 모델은 폐기됨.
        """
        if self.estimated_amount is None or self.probability is None:
            return 0.0
        return self.estimated_amount * (self.probability / 100.0)

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "Sale":
        props = page.get("properties", {})
        sub_start, _ = P.date_range(props, "제출일")
        return cls(
            id=page.get("id", ""),
            code=P.rich_text(props, "영업코드"),
            name=P.title(props, "견적서명"),
            kind=P.select_name(props, "유형"),
            stage=P.select_name(props, "단계"),
            category=P.multi_select_names(props, "업무내용"),
            estimated_amount=P.number(props, "견적금액"),
            probability=P.number(props, "수주확률"),
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


class SaleCreateRequest(BaseModel):
    """영업 생성 요청. 노션 견적서 작성 리스트에 새 페이지를 추가."""

    name: str  # 견적서명
    code: str = ""  # 영업코드 — 빈 문자열이면 backend가 {YY}-영업-{NNN}으로 자동 부여
    kind: str = ""  # 수주영업|기술지원
    stage: str = ""
    category: list[str] = []
    estimated_amount: float | None = None
    probability: float | None = None  # 수주확률 0~100 (PM 직접 입력)
    is_bid: bool = False
    client_id: str = ""
    gross_floor_area: float | None = None
    floors_above: float | None = None
    floors_below: float | None = None
    building_count: float | None = None
    note: str = ""
    submission_date: str | None = None
    vat_inclusive: str = ""
    performance_design_amount: float | None = None
    wind_tunnel_amount: float | None = None
    parent_lead_id: str = ""
    assignees: list[str] = []


class SaleUpdateRequest(BaseModel):
    """영업 수정 요청. None이 아닌 필드만 노션 properties로 변환."""

    name: str | None = None
    code: str | None = None  # 노션에서 수동 수정 허용 (자동 부여 후 변경 가능)
    kind: str | None = None
    stage: str | None = None
    category: list[str] | None = None
    estimated_amount: float | None = None
    probability: float | None = None
    is_bid: bool | None = None
    client_id: str | None = None
    gross_floor_area: float | None = None
    floors_above: float | None = None
    floors_below: float | None = None
    building_count: float | None = None
    note: str | None = None
    submission_date: str | None = None
    vat_inclusive: str | None = None
    performance_design_amount: float | None = None
    wind_tunnel_amount: float | None = None
    parent_lead_id: str | None = None
    assignees: list[str] | None = None


# ── DTO → 노션 properties 변환 ──


def _title(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value}}]}


def _rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": value}}]}


def _select(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {"select": {"name": value}}


def _multi_select(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": v} for v in values]}


def _relation(ids: list[str]) -> dict[str, Any]:
    return {"relation": [{"id": i} for i in ids if i]}


def _number(value: float | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"number": value}


def _date(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {"date": {"start": value}}


def sale_create_to_props(req: SaleCreateRequest) -> dict[str, Any]:
    """SaleCreateRequest → 노션 properties dict.

    빈 값은 노션에 보내지 않아 default를 노션이 적용하도록 한다.
    영업코드는 라우터에서 자동 부여 후 req.code에 채워서 전달.
    """
    props: dict[str, Any] = {"견적서명": _title(req.name)}
    if req.code:
        props["영업코드"] = _rich_text(req.code)
    if req.kind:
        props["유형"] = {"select": {"name": req.kind}}
    if req.stage:
        props["단계"] = {"select": {"name": req.stage}}
    if req.category:
        props["업무내용"] = _multi_select(req.category)
    n = _number(req.estimated_amount)
    if n is not None:
        props["견적금액"] = n
    n = _number(req.probability)
    if n is not None:
        props["수주확률"] = n
    if req.is_bid:
        props["입찰여부"] = {"checkbox": True}
    if req.client_id:
        props["의뢰처"] = _relation([req.client_id])
    for col, val in [
        ("연면적", req.gross_floor_area),
        ("지상층수", req.floors_above),
        ("지하층수", req.floors_below),
        ("동수", req.building_count),
        ("성능설계", req.performance_design_amount),
        ("풍동실험", req.wind_tunnel_amount),
    ]:
        n = _number(val)
        if n is not None:
            props[col] = n
    if req.note:
        props["비고"] = _rich_text(req.note)
    d = _date(req.submission_date)
    if d:
        props["제출일"] = d
    if req.vat_inclusive:
        props["VAT포함"] = {"select": {"name": req.vat_inclusive}}
    if req.parent_lead_id:
        props["상위 영업건"] = _relation([req.parent_lead_id])
    if req.assignees:
        props["담당자"] = _multi_select(req.assignees)
    return props


def sale_update_to_props(req: SaleUpdateRequest) -> dict[str, Any]:
    """SaleUpdateRequest → 노션 properties dict.

    None이 아닌 필드만 변환. 빈 문자열은 'clear' 신호로 select=None 등 처리.
    """
    props: dict[str, Any] = {}
    if req.name is not None:
        props["견적서명"] = _title(req.name)
    if req.code is not None:
        props["영업코드"] = _rich_text(req.code)
    if req.kind is not None:
        props["유형"] = (
            {"select": None} if req.kind == "" else {"select": {"name": req.kind}}
        )
    if req.stage is not None:
        props["단계"] = (
            {"select": None} if req.stage == "" else {"select": {"name": req.stage}}
        )
    if req.category is not None:
        props["업무내용"] = _multi_select(req.category)
    if req.estimated_amount is not None:
        props["견적금액"] = {"number": req.estimated_amount}
    if req.probability is not None:
        props["수주확률"] = {"number": req.probability}
    if req.is_bid is not None:
        props["입찰여부"] = {"checkbox": req.is_bid}
    if req.client_id is not None:
        props["의뢰처"] = _relation([req.client_id] if req.client_id else [])
    for col, val in [
        ("연면적", req.gross_floor_area),
        ("지상층수", req.floors_above),
        ("지하층수", req.floors_below),
        ("동수", req.building_count),
        ("성능설계", req.performance_design_amount),
        ("풍동실험", req.wind_tunnel_amount),
    ]:
        if val is not None:
            props[col] = {"number": val}
    if req.note is not None:
        props["비고"] = _rich_text(req.note)
    if req.submission_date is not None:
        props["제출일"] = (
            {"date": None} if req.submission_date == "" else {"date": {"start": req.submission_date}}
        )
    if req.vat_inclusive is not None:
        props["VAT포함"] = (
            {"select": None}
            if req.vat_inclusive == ""
            else {"select": {"name": req.vat_inclusive}}
        )
    if req.parent_lead_id is not None:
        props["상위 영업건"] = _relation(
            [req.parent_lead_id] if req.parent_lead_id else []
        )
    if req.assignees is not None:
        props["담당자"] = _multi_select(req.assignees)
    return props
