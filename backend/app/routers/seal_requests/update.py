"""날인요청 update / redo endpoint.

PR-CJ (Phase 4-J 8단계): seal_requests/__init__.py에서 update + redo 분리.
- PATCH /:id — 재요청용 텍스트 필드 update + 반려→1차검토 복구
- POST /:id/redo — 재날인요청 (같은 row 새 사이클 덮어쓰기)

`SealUpdateBody` + `SealRedoBody` model도 함께 이동 (이 endpoint들에서만 사용).
다른 helper는 함수 안 lazy import.
`SealRequestItem`은 decorator(`response_model`)에 필요해 module-level lazy import.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services import seal_logic as SL
from app.services.notion import NotionService, get_notion

router = APIRouter()

# module-level lazy import — sub-router include가 파일 끝(__init__.py fully loaded 후).
from app.routers.seal_requests import SealRequestItem  # noqa: E402


class SealUpdateBody(BaseModel):
    """재요청 시 텍스트 필드 일괄 수정.

    None인 필드는 변경 안 함. 빈 문자열은 'clear' 신호.
    real_source_id: 거래처 page_id. ""면 relation 비움.
    """

    title: str | None = None
    real_source_id: str | None = None
    purpose: str | None = None
    revision: int | None = None
    with_safety_cert: bool | None = None
    summary: str | None = None
    doc_kind: str | None = None
    note: str | None = None
    due_date: str | None = None


class SealRedoBody(BaseModel):
    """재날인요청 — 같은 노션 row를 새 1차검토 사이클로 덮어쓰기.

    create와 동일한 모든 입력을 받음. seal_type은 변경 가능(요구상 모든 필드
    덮어쓰기). 단 구조검토서는 새 문서번호로 자동 갱신.
    """

    seal_type: str
    due_date: str
    title: str = ""
    note: str = ""
    real_source_id: str = ""
    purpose: str = ""
    revision: int = 0
    with_safety_cert: bool = False
    summary: str = ""
    doc_kind: str = ""


@router.patch("/{page_id}", response_model=SealRequestItem)
async def update_seal_request(
    page_id: str,
    body: SealUpdateBody,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """재요청용 텍스트 필드 update. 본인 또는 admin/team_lead만,
    상태가 '반려' 또는 '1차검토 중'(아직 처리 전)일 때만 허용.
    상태가 '반려'였으면 '1차검토 중'으로 복구 + Bot 알림 재발송.
    """
    from app.routers.seal_requests import (
        _bot_send,
        _can_access,
        _create_seal_task_bg,
        _find_admins,
        _find_team_lead,
        _from_notion_page,
        _get_title_prop_name,
        _resolve_works_id,
        _spawn_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    is_lead_admin = user.role in {"admin", "team_lead"}
    if not (is_owner or is_lead_admin):
        raise HTTPException(status_code=403, detail="본인 요청만 수정 가능")
    cur_status = SL.normalize_status(P.select_name(props, "상태"))
    if cur_status not in {"1차검토 중", "반려"}:
        raise HTTPException(
            status_code=400,
            detail=f"수정 가능 상태가 아님 (현재: {cur_status or '미정'})",
        )

    update_props: dict[str, Any] = {}
    if body.title is not None:
        title_prop = await _get_title_prop_name(notion)
        update_props[title_prop] = {
            "title": [{"text": {"content": body.title}}]
        }
    if body.real_source_id is not None:
        update_props["실제출처"] = (
            {"relation": []}
            if body.real_source_id == ""
            else {"relation": [{"id": body.real_source_id}]}
        )
    if body.purpose is not None:
        update_props["용도"] = {
            "rich_text": [{"text": {"content": body.purpose}}]
        }
    if body.revision is not None:
        update_props["Revision"] = {"number": int(body.revision)}
    if body.with_safety_cert is not None:
        update_props["안전확인서포함"] = {"checkbox": bool(body.with_safety_cert)}
    if body.summary is not None:
        update_props["내용요약"] = {
            "rich_text": [{"text": {"content": body.summary}}]
        }
    if body.doc_kind is not None:
        update_props["문서종류"] = {
            "rich_text": [{"text": {"content": body.doc_kind}}]
        }
    if body.note is not None:
        update_props["비고"] = {
            "rich_text": [{"text": {"content": body.note}}]
        }
    if body.due_date is not None:
        update_props["제출예정일"] = (
            {"date": None} if body.due_date == "" else {"date": {"start": body.due_date}}
        )

    # 반려 → 1차검토 중 복구 + 처리자/처리일 reset
    if cur_status == "반려":
        update_props["상태"] = {"select": {"name": "1차검토 중"}}
        update_props["팀장처리자"] = {"rich_text": [{"text": {"content": ""}}]}
        update_props["팀장처리일"] = {"date": None}

    if update_props:
        await notion.update_page(page_id, update_props)

    # 반려 → 재요청이면 알림 재발송 + 1차 검토자 TASK 재생성 (이전 반려 시 완료됨)
    if cur_status == "반려":
        item = _from_notion_page(page)
        # 새 1차 검토자 결정 — 등록 흐름과 동일 규칙
        new_lead_name = ""
        if user.role == "member":
            lead = _find_team_lead(db, requester_name=requester)
            if lead:
                new_lead_name = lead.name or ""
            else:
                admins_for_task = _find_admins(db)
                if admins_for_task:
                    new_lead_name = admins_for_task[0].name or ""
        else:
            admins_for_task = _find_admins(db)
            if admins_for_task:
                new_lead_name = admins_for_task[0].name or ""
        if item.project_ids and new_lead_name:
            _spawn_task(
                _create_seal_task_bg(
                    notion,
                    seal_page_id=page_id,
                    seal_link_prop="1차검토TASK",
                    project_id=item.project_ids[0],
                    title=f"[날인 1차검토(재요청)] {body.title or item.title}",
                    assignee_name=new_lead_name,
                    today_iso=date.today().isoformat(),
                )
            )

        msg = (
            f"[날인 재요청] {body.title or item.title}"
            f"\n요청자: {requester}"
        )
        if user.role == "member":
            lead = _find_team_lead(db, requester_name=requester)
            if lead:
                _bot_send(_resolve_works_id(lead), msg)
            else:
                for adm in _find_admins(db):
                    _bot_send(_resolve_works_id(adm), msg)
        else:
            # team_lead 또는 admin이 재요청 → admin 전원 (본인 포함)
            for adm in _find_admins(db):
                _bot_send(_resolve_works_id(adm), msg)

    updated = await notion.get_page(page_id)
    return _from_notion_page(updated)


@router.post("/{page_id}/redo", response_model=SealRequestItem)
async def redo_seal_request(
    page_id: str,
    body: SealRedoBody,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """재날인요청 — 같은 노션 row를 update해 새 1차검토 사이클 시작.

    docs/request.md 정책:
    - DB row는 새로 만들지 않고 기존 row 덮어쓰기.
    - 모든 입력 필드를 update + 상태='1차검토 중' + 처리자/반려사유 reset.
    - 구조검토서의 문서번호는 이전 값 유지(새로 발급 X).
    - 자동 TASK 흐름은 정상 — 요청자 + 1차 검토자 TASK를 새로 생성.
      (이전 사이클의 TASK들은 완료 상태 그대로 보존하여 history.)
    """
    from app.routers.seal_requests import (
        _bot_send,
        _can_access,
        _create_seal_task_bg,
        _find_admins,
        _find_team_lead,
        _from_notion_page,
        _get_title_prop_name,
        _project_summary_from_db,
        _resolve_works_id,
        _spawn_task,
    )

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자") or (user.name or user.username)
    project_ids = P.relation_ids(props, "프로젝트")
    if not project_ids:
        raise HTTPException(status_code=400, detail="프로젝트 relation 누락")
    project_id = project_ids[0]

    seal_type = SL.normalize_type(body.seal_type.strip())
    if seal_type not in SL.SEAL_TYPES_NEW:
        raise HTTPException(
            status_code=400, detail=f"잘못된 날인유형: {seal_type}"
        )
    due_iso = (body.due_date or "").strip()
    if not due_iso:
        raise HTTPException(status_code=400, detail="제출예정일은 필수입니다")

    today = date.today()
    today_iso = today.isoformat()

    # 1) 검토구분별 필드 정리. 구조검토서 문서번호는 기존 값 유지.
    fields: dict[str, Any] = {}
    if seal_type == "구조계산서":
        fields = {"revision": body.revision, "용도": body.purpose}
    elif seal_type in {"구조안전확인서", "구조도면"}:
        fields = {"용도": body.purpose}
    elif seal_type == "구조검토서":
        existing_doc_no = P.rich_text(props, "문서번호").strip()
        fields = {"문서번호": existing_doc_no, "내용요약": body.summary}
    elif seal_type == "기타":
        fields = {"문서종류": body.doc_kind}

    # 2) 자동 제목 (사용자 입력 우선) — 새 등록과 동일 빌더
    code, project_name, _drive_url, _root_folder_id = _project_summary_from_db(
        db, project_id
    )
    auto_title = (body.title or "").strip() or SL.build_title(
        code=code, seal_type=seal_type, fields=fields
    )

    # 3) 기존 row 덮어쓰기 — 모든 prop + 상태/처리자 reset
    title_prop = await _get_title_prop_name(notion)
    update_props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": auto_title}}]},
        "날인유형": {"select": {"name": seal_type}},
        "상태": {"select": {"name": "1차검토 중"}},
        "요청일": {"date": {"start": today_iso}},
        "제출예정일": {"date": {"start": due_iso}},
        "비고": {"rich_text": [{"text": {"content": body.note}}]},
        # 이전 사이클 처리/반려 정보 reset
        "팀장처리자": {"rich_text": [{"text": {"content": ""}}]},
        "팀장처리일": {"date": None},
        "관리자처리자": {"rich_text": [{"text": {"content": ""}}]},
        "관리자처리일": {"date": None},
        "반려사유": {"rich_text": [{"text": {"content": ""}}]},
        # 새 사이클 — 검토자 TASK ID는 비워두고 새 task 생성 후 채움
        "1차검토TASK": {"rich_text": [{"text": {"content": ""}}]},
        "2차검토TASK": {"rich_text": [{"text": {"content": ""}}]},
    }
    if body.real_source_id.strip():
        update_props["실제출처"] = {
            "relation": [{"id": body.real_source_id.strip()}]
        }
    else:
        update_props["실제출처"] = {"relation": []}
    if seal_type == "구조계산서":
        update_props["Revision"] = {"number": int(body.revision or 0)}
        update_props["안전확인서포함"] = {"checkbox": bool(body.with_safety_cert)}
    if "용도" in fields:
        update_props["용도"] = {
            "rich_text": [{"text": {"content": str(fields["용도"] or "")}}]
        }
    if seal_type == "구조검토서":
        # 문서번호는 그대로 두지만 명시적으로 다시 set (idempotent)
        update_props["문서번호"] = {
            "rich_text": [{"text": {"content": str(fields.get("문서번호", ""))}}]
        }
        update_props["내용요약"] = {
            "rich_text": [{"text": {"content": body.summary}}]
        }
    if seal_type == "기타":
        update_props["문서종류"] = {
            "rich_text": [{"text": {"content": body.doc_kind.strip()}}]
        }

    await notion.update_page(page_id, update_props)

    # 4) 자동 TASK 새로 생성 — 요청자 + 1차 검토자
    _spawn_task(
        _create_seal_task_bg(
            notion,
            seal_page_id=page_id,
            seal_link_prop="연결TASK",
            project_id=project_id,
            title=f"[날인 재요청] {auto_title}",
            assignee_name=requester,
            today_iso=today_iso,
        )
    )
    lead_reviewer_name = ""
    if user.role == "member":
        lead = _find_team_lead(db, requester_name=requester)
        if lead:
            lead_reviewer_name = lead.name or ""
        else:
            admins_list = _find_admins(db)
            if admins_list:
                lead_reviewer_name = admins_list[0].name or ""
    else:
        admins_list = _find_admins(db)
        if admins_list:
            lead_reviewer_name = admins_list[0].name or ""
    _spawn_task(
        _create_seal_task_bg(
            notion,
            seal_page_id=page_id,
            seal_link_prop="1차검토TASK",
            project_id=project_id,
            title=f"[날인 1차검토(재요청)] {auto_title}",
            assignee_name=lead_reviewer_name,
            today_iso=today_iso,
        )
    )

    # 5) Bot 알림
    project_label = (
        f"[{code}] {project_name}".strip("[] ") or project_name or project_id
    )
    msg = (
        f"[날인 재요청] {project_label} - {seal_type} ({auto_title})"
        f"\n요청자: {requester} / 제출예정일: {due_iso}"
    )
    if user.role == "member":
        lead = _find_team_lead(db, requester_name=requester)
        if lead:
            _bot_send(_resolve_works_id(lead), msg)
        else:
            for adm in _find_admins(db):
                _bot_send(_resolve_works_id(adm), msg)
    else:
        for adm in _find_admins(db):
            _bot_send(_resolve_works_id(adm), msg)

    final = await notion.get_page(page_id)
    return _from_notion_page(final)
