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
    master_project_id: str = "" # Master Project relation 첫 번째 page id
    master_project_name: str = ""  # Master Project 의 용역명 (resolve_master_names 로 채움)
    name: str                   # 프로젝트명 (title)

    # 발주처
    client_text: str = ""       # 발주처(임시) (정식 발주처 relation은 별도 조회)
    client_relation_ids: list[str] = []
    client_names: list[str] = []  # 발주처 relation 이름 해결 결과 (선택, 빈 배열이면 미해결)

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
    # NAVER WORKS Drive 폴더 URL (Phase 2 — 자동 생성됨, 노션 'WORKS Drive URL' 컬럼)
    drive_url: str = ""

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "Project":
        props = page.get("properties", {})
        cs, ce = P.date_range(props, "계약기간")
        master_ids = P.relation_ids(props, "Master Project")
        return cls(
            id=page.get("id", ""),
            code=P.rich_text(props, "Sub_CODE"),
            master_code=str(P.rollup_value(props, "Master Code") or ""),
            master_project_id=master_ids[0] if master_ids else "",
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
            # NAVER WORKS Drive URL의 path가 'share/root-folder'면 sharedrive root로
            # redirect되어 resourceKey가 무시됨. 'share/folder'로 정규화해 정확한
            # 폴더로 이동하도록 함. 기존 노션에 저장된 잘못된 URL을 자동 회복.
            drive_url=P.url(props, "WORKS Drive URL").replace(
                "/share/root-folder?", "/share/folder?"
            ),
        )


class ProjectListResponse(BaseModel):
    items: list[Project]
    count: int


class ProjectCreateRequest(BaseModel):
    """노션 메인 프로젝트 DB에 새 페이지 생성 요청."""

    name: str
    code: str = ""
    client_text: str = ""                 # 협력업체 미매칭 시 fallback (text 컬럼)
    client_relation_ids: list[str] = []   # 협력업체 DB page_id (선택 시)
    stage: str = "진행중"
    teams: list[str] = []
    assignees: list[str] = []
    work_types: list[str] = []
    start_date: str | None = None
    contract_start: str | None = None
    contract_end: str | None = None
    contract_amount: float | None = None


class ProjectUpdateRequest(BaseModel):
    """노션 메인 프로젝트 DB 페이지 부분 갱신 요청. None 인 필드는 변경 안 함."""

    name: str | None = None
    code: str | None = None
    client_text: str | None = None
    client_relation_ids: list[str] | None = None
    stage: str | None = None
    teams: list[str] | None = None
    assignees: list[str] | None = None
    work_types: list[str] | None = None
    start_date: str | None = None
    contract_start: str | None = None
    contract_end: str | None = None
    contract_amount: float | None = None
    vat: float | None = None


def project_update_to_props(req: ProjectUpdateRequest) -> dict[str, Any]:
    """None이 아닌 필드만 노션 properties로 변환. 빈 문자열은 'clear' 신호."""
    props: dict[str, Any] = {}
    if req.name is not None:
        props["프로젝트명"] = {"title": [{"text": {"content": req.name}}]}
    if req.code is not None:
        props["Sub_CODE"] = {"rich_text": [{"text": {"content": req.code}}]}
    if req.client_text is not None:
        props["발주처(임시)"] = {"rich_text": [{"text": {"content": req.client_text}}]}
    if req.client_relation_ids is not None:
        props["발주처"] = {"relation": [{"id": rid} for rid in req.client_relation_ids]}
    if req.stage is not None and req.stage != "":
        props["진행단계"] = {"select": {"name": req.stage}}
    if req.teams is not None:
        props["담당팀"] = {"multi_select": [{"name": t} for t in req.teams]}
    if req.assignees is not None:
        props["담당자"] = {"multi_select": [{"name": a} for a in req.assignees]}
    if req.work_types is not None:
        props["업무내용"] = {"multi_select": [{"name": w} for w in req.work_types]}
    if req.start_date is not None:
        props["시작일"] = (
            {"date": None}
            if req.start_date == ""
            else {"date": {"start": req.start_date, "end": None}}
        )
    if req.contract_start is not None or req.contract_end is not None:
        if req.contract_start == "" and (
            req.contract_end is None or req.contract_end == ""
        ):
            props["계약기간"] = {"date": None}
        else:
            props["계약기간"] = {
                "date": {
                    "start": req.contract_start or None,
                    "end": req.contract_end or None,
                }
            }
    if req.contract_amount is not None:
        props["용역비(VAT제외)"] = {"number": req.contract_amount}
    if req.vat is not None:
        props["VAT"] = {"number": req.vat}
    return props


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
    if req.client_relation_ids:
        props["발주처"] = {
            "relation": [{"id": rid} for rid in req.client_relation_ids]
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
