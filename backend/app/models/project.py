"""프로젝트 DTO — 노션 메인 DB 페이지를 우리 앱이 사용할 형태로 변환."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services import notion_props as P


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # 식별
    id: str
    code: str = ""              # Sub_CODE
    master_code: str = ""       # Master Code (rollup)
    name: str                   # 프로젝트명 (title)

    # 발주처
    client_text: str = ""       # 발주처(임시) (정식 발주처 relation은 별도 조회)
    client_relation_ids: list[str] = []

    # 상태
    stage: str = ""             # 진행단계 (진행중/대기/보류/완료/타절/종결/이관)
    contract_signed: bool = False  # 계약 checkbox
    completed: bool = False        # 완료 checkbox

    # 일정
    start_date: str | None = None         # 시작일 (수주확정)
    contract_start: str | None = None     # 계약기간 start
    contract_end: str | None = None       # 계약기간 end
    end_date: str | None = None           # 완료일

    # 사람
    assignees: list[str] = []   # 담당자
    teams: list[str] = []       # 담당팀

    # 업무
    work_types: list[str] = []  # 업무내용

    # 금액
    contract_amount: float | None = None   # 용역비(VAT제외)
    vat: float | None = None
    method_review_fee: float | None = None  # 공법검토비
    progress_payment: float | None = None   # 기성금
    outsourcing_estimated: float | None = None  # 외주비(예정)

    # 집계 (rollup/formula)
    collection_rate: Any = None        # 수금률 (formula)
    collection_total: float | None = None  # 수금합 (rollup sum)
    expense_total: float | None = None     # 지출(외주비포함) (rollup sum)

    # 메타
    last_edited_time: str | None = None
    url: str | None = None

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "Project":
        props = page.get("properties", {})
        cs, ce = P.date_range(props, "계약기간")
        return cls(
            id=page.get("id", ""),
            code=P.rich_text(props, "Sub_CODE"),
            master_code=str(P.rollup_value(props, "Master Code") or ""),
            name=P.title(props, "프로젝트명"),
            client_text=P.rich_text(props, "발주처(임시)"),
            client_relation_ids=P.relation_ids(props, "발주처"),
            stage=P.select_name(props, "진행단계"),
            contract_signed=P.checkbox(props, "계약"),
            completed=P.checkbox(props, "완료"),
            start_date=P.date_range(props, "시작일")[0],
            contract_start=cs,
            contract_end=ce,
            end_date=P.date_range(props, "완료일")[0],
            assignees=P.multi_select_names(props, "담당자"),
            teams=P.multi_select_names(props, "담당팀"),
            work_types=P.multi_select_names(props, "업무내용"),
            contract_amount=P.number(props, "용역비(VAT제외)"),
            vat=P.number(props, "VAT"),
            method_review_fee=P.number(props, "공법검토비"),
            progress_payment=P.number(props, "기성금"),
            outsourcing_estimated=P.number(props, "외주비(예정)"),
            collection_rate=P.formula_value(props, "수금률"),
            collection_total=P.rollup_value(props, "수금합"),
            expense_total=P.rollup_value(props, "지출(외주비포함)"),
            last_edited_time=page.get("last_edited_time"),
            url=page.get("url"),
        )


class ProjectListResponse(BaseModel):
    items: list[Project]
    count: int


class ProjectCreateRequest(BaseModel):
    """노션 메인 프로젝트 DB에 새 페이지 생성 요청."""

    name: str
    code: str = ""
    client_text: str = ""
    stage: str = "진행중"
    teams: list[str] = []
    assignees: list[str] = []
    work_types: list[str] = []
    start_date: str | None = None
    contract_start: str | None = None
    contract_end: str | None = None
    contract_amount: float | None = None


def project_create_to_props(req: ProjectCreateRequest) -> dict[str, Any]:
    """노션 페이지 생성용 properties 변환."""
    props: dict[str, Any] = {
        "프로젝트명": {"title": [{"text": {"content": req.name}}]},
    }
    if req.code:
        props["Sub_CODE"] = {"rich_text": [{"text": {"content": req.code}}]}
    if req.client_text:
        props["발주처(임시)"] = {
            "rich_text": [{"text": {"content": req.client_text}}]
        }
    if req.stage:
        props["진행단계"] = {"select": {"name": req.stage}}
    if req.teams:
        props["담당팀"] = {"multi_select": [{"name": t} for t in req.teams]}
    if req.assignees:
        props["담당자"] = {
            "multi_select": [{"name": a} for a in req.assignees]
        }
    if req.work_types:
        props["업무내용"] = {
            "multi_select": [{"name": w} for w in req.work_types]
        }
    if req.start_date:
        props["시작일"] = {"date": {"start": req.start_date, "end": None}}
    if req.contract_start or req.contract_end:
        props["계약기간"] = {
            "date": {
                "start": req.contract_start or req.start_date,
                "end": req.contract_end,
            }
        }
    if req.contract_amount is not None:
        props["용역비(VAT제외)"] = {"number": req.contract_amount}
    return props
