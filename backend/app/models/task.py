"""업무TASK DTO + 노션 properties 변환."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.services import notion_props as P


class Task(BaseModel):
    """노션 업무TASK DB 페이지를 우리 앱이 사용할 형태로 변환한 DTO."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str = ""
    code: str = ""
    project_ids: list[str] = []  # 프로젝트 relation
    status: str = ""             # status (시작 전/진행 중/완료/보류)
    progress: float | None = None  # 0.0 ~ 1.0
    start_date: str | None = None
    end_date: str | None = None
    actual_end_date: str | None = None
    priority: str = ""
    assignees: list[str] = []
    teams: list[str] = []
    note: str = ""
    created_time: str | None = None
    last_edited_time: str | None = None
    url: str | None = None

    @classmethod
    def from_notion_page(cls, page: dict[str, Any]) -> "Task":
        props = page.get("properties", {})
        s, e = P.date_range(props, "기간")
        return cls(
            id=page.get("id", ""),
            title=P.title(props, "내용"),
            code=P.rich_text(props, "CODE"),
            project_ids=P.relation_ids(props, "프로젝트"),
            status=P.status_name(props, "상태"),
            progress=P.number(props, "진행률"),
            start_date=s,
            end_date=e,
            actual_end_date=P.date_range(props, "실제 완료일")[0],
            priority=P.select_name(props, "우선순위"),
            assignees=P.multi_select_names(props, "담당자"),
            teams=P.multi_select_names(props, "담당팀"),
            note=P.rich_text(props, "비고"),
            created_time=page.get("created_time"),
            last_edited_time=page.get("last_edited_time"),
            url=page.get("url"),
        )


class TaskCreateRequest(BaseModel):
    title: str
    project_id: str  # 부모 프로젝트 1개 (단일 관계로 단순화)
    status: str | None = None
    progress: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    priority: str | None = None
    assignees: list[str] = []
    teams: list[str] = []
    note: str = ""
    code: str = ""


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    progress: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    actual_end_date: str | None = None
    priority: str | None = None
    assignees: list[str] | None = None
    teams: list[str] | None = None
    note: str | None = None


class TaskListResponse(BaseModel):
    items: list[Task]
    count: int


# ── DTO → 노션 properties 변환 ──


def _date_prop(start: str | None, end: str | None) -> dict[str, Any] | None:
    if not start and not end:
        return None
    return {"date": {"start": start, "end": end}}


def _multi_select(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": v} for v in values]}


def _select(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {"select": {"name": value}}


def _status(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {"status": {"name": value}}


def _rich_text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": value}}]}


def _title(value: str) -> dict[str, Any]:
    return {"title": [{"text": {"content": value}}]}


def _number(value: float | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"number": value}


def _relation(ids: list[str]) -> dict[str, Any]:
    return {"relation": [{"id": i} for i in ids if i]}


def task_create_to_props(req: TaskCreateRequest) -> dict[str, Any]:
    props: dict[str, Any] = {
        "내용": _title(req.title),
        "프로젝트": _relation([req.project_id]),
    }
    if req.code:
        props["CODE"] = _rich_text(req.code)
    if req.assignees:
        props["담당자"] = _multi_select(req.assignees)
    if req.teams:
        props["담당팀"] = _multi_select(req.teams)
    st = _status(req.status)
    if st:
        props["상태"] = st
    n = _number(req.progress)
    if n is not None:
        props["진행률"] = n
    d = _date_prop(req.start_date, req.end_date)
    if d:
        props["기간"] = d
    pri = _select(req.priority)
    if pri:
        props["우선순위"] = pri
    if req.note:
        props["비고"] = _rich_text(req.note)
    return props


def task_update_to_props(req: TaskUpdateRequest) -> dict[str, Any]:
    """None 이 아닌 필드만 properties 로 변환."""
    props: dict[str, Any] = {}
    if req.title is not None:
        props["내용"] = _title(req.title)
    if req.status is not None:
        st = _status(req.status)
        if st:
            props["상태"] = st
    if req.progress is not None:
        props["진행률"] = {"number": req.progress}
    if req.start_date is not None or req.end_date is not None:
        d = _date_prop(req.start_date, req.end_date)
        if d:
            props["기간"] = d
    if req.actual_end_date is not None:
        d = _date_prop(req.actual_end_date, None)
        if d:
            props["실제 완료일"] = d
    if req.priority is not None:
        pri = _select(req.priority)
        if pri:
            props["우선순위"] = pri
    if req.assignees is not None:
        props["담당자"] = _multi_select(req.assignees)
    if req.teams is not None:
        props["담당팀"] = _multi_select(req.teams)
    if req.note is not None:
        props["비고"] = _rich_text(req.note)
    return props
