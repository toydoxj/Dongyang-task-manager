"""날인요청 create endpoint (POST /).

PR-CW (Phase 4-J 12단계): seal_requests/__init__.py에서 create_seal_request 분리.
가장 큰 endpoint(~165 lines). 흐름: 노션 page 생성 → Drive 업로드 → 첨부메타 update
→ 자동 TASK 생성 → Bot 알림 → final fetch + mirror upsert.

list와 동일하게 path가 ""라 sub-router로 mount 불가 → 함수만 export →
__init__.py에서 add_api_route로 직접 등록.

상위 router(`prefix="/seal-requests"`)가 prefix 상속.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P  # noqa: F401  (호환 import)
from app.services import seal_logic as SL
from app.services import sso_drive
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.seal_requests.create")

# module-level lazy import — __init__.py가 fully loaded 시점.
from app.routers.seal_requests import SealRequestItem  # noqa: E402


def _db_id() -> str:
    """meta.py / delete.py / list_endpoint.py와 동일 helper (외과적, 2줄)."""
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(status_code=500, detail="NOTION_DB_SEAL_REQUESTS 미설정")
    return db_id


async def create_seal_request(
    project_id: str = Form(..., description="노션 프로젝트 page_id"),
    seal_type: str = Form(..., description="구조계산서/구조안전확인서/구조검토서/구조도면/보고서/기타"),
    due_date: str = Form(..., description="제출 예정일 (YYYY-MM-DD, 필수)"),
    title: str = Form("", description="제목 (생략 시 자동 생성)"),
    note: str = Form(""),
    real_source_id: str = Form(
        "", description="실제출처 거래처 page_id (발주처와 다른 경우만)"
    ),
    purpose: str = Form("", description="용도 — 구조계산서/구조안전확인서/구조도면"),
    revision: int = Form(0, description="Revision — 구조계산서"),
    with_safety_cert: bool = Form(False, description="안전확인서포함 — 구조계산서"),
    summary: str = Form("", description="내용요약 — 구조검토서"),
    doc_kind: str = Form("", description="문서종류 — 기타"),
    files: list[UploadFile] = File([], description="첨부 파일 (선택, 다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    from app.routers.seal_requests import (
        _attachments_to_meta_json,
        _bot_send,
        _create_seal_task_bg,
        _failed_to_partial,
        _find_admins,
        _find_team_lead,
        _from_notion_page,
        _get_title_prop_name,
        _max_bytes,
        _project_summary_from_db,
        _read_with_limit,
        _resolve_works_id,
        _spawn_task,
    )

    seal_type = SL.normalize_type(seal_type.strip())
    if seal_type not in SL.SEAL_TYPES_NEW:
        raise HTTPException(
            status_code=400, detail=f"잘못된 날인유형: {seal_type}"
        )
    due_iso = (due_date or "").strip()
    if not due_iso:
        raise HTTPException(status_code=400, detail="제출예정일은 필수입니다")

    requester = user.name or user.username
    today = date.today()
    today_iso = today.isoformat()

    # 1) 검토구분별 필드 정리 + 구조검토서는 문서번호 발급
    fields: dict[str, Any] = {}
    if seal_type == "구조계산서":
        fields = {"revision": revision, "용도": purpose}
    elif seal_type in {"구조안전확인서", "구조도면"}:
        fields = {"용도": purpose}
    elif seal_type == "구조검토서":
        doc_no = await SL.issue_review_doc_number(notion, _db_id())
        fields = {"문서번호": doc_no, "내용요약": summary}
    elif seal_type == "기타":
        fields = {"문서종류": doc_kind}
    # 보고서: 추가 필드 없음

    # 2) 자동 제목 (사용자 입력 우선)
    code, project_name, drive_url, root_folder_id = _project_summary_from_db(
        db, project_id
    )
    auto_title = (title or "").strip() or SL.build_title(
        code=code, seal_type=seal_type, fields=fields
    )

    max_bytes = _max_bytes()

    # 3) 노션 page 먼저 생성 (page_id 확보)
    title_prop = await _get_title_prop_name(notion)
    init_props: dict[str, Any] = {
        title_prop: {"title": [{"text": {"content": auto_title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "날인유형": {"select": {"name": seal_type}},
        "상태": {"select": {"name": "1차검토 중"}},
        "요청자": {"rich_text": [{"text": {"content": requester}}]},
        "요청일": {"date": {"start": today_iso}},
        "제출예정일": {"date": {"start": due_iso}},
        "비고": {"rich_text": [{"text": {"content": note}}]},
    }
    if real_source_id.strip():
        init_props["실제출처"] = {
            "relation": [{"id": real_source_id.strip()}]
        }
    if seal_type == "구조계산서":
        init_props["Revision"] = {"number": int(revision or 0)}
        init_props["안전확인서포함"] = {"checkbox": bool(with_safety_cert)}
    if "용도" in fields:
        init_props["용도"] = {
            "rich_text": [{"text": {"content": str(fields["용도"] or "")}}]
        }
    if seal_type == "구조검토서":
        init_props["문서번호"] = {
            "rich_text": [{"text": {"content": str(fields.get("문서번호", ""))}}]
        }
        init_props["내용요약"] = {
            "rich_text": [{"text": {"content": summary}}]
        }
    if seal_type == "기타":
        init_props["문서종류"] = {
            "rich_text": [{"text": {"content": doc_kind.strip()}}]
        }

    page = await notion.create_page(_db_id(), init_props)
    page_id = page["id"]

    # 4) 검토자료 폴더 — 사용자가 모달에서 [폴더생성]으로 미리 만든 폴더만 사용.
    # backend 자동 ensure는 하지 않음. 못 찾으면 빈 채로 둠.
    attachments_meta: list[dict[str, Any]] = []
    failed: list[str] = []
    folder_url = ""
    s_set = get_settings()
    day_folder_id = ""
    if s_set.works_drive_enabled and root_folder_id:
        ymd = today.strftime("%Y%m%d")
        found = await sso_drive.find_review_folder(root_folder_id, ymd)
        if found:
            day_folder_id, folder_url = found
    if not day_folder_id and files:
        failed.extend(
            [f"{(f.filename or 'file.bin')}: 검토자료 폴더 미생성" for f in files]
        )

    # 호환: 첨부 파일이 들어오면 기존 로직 그대로 (frontend는 더 이상 안 보냄).
    if files and day_folder_id:
        for f in files:
            fname = f.filename or "file.bin"
            data = await _read_with_limit(f, max_bytes)
            if data is None:
                failed.append(
                    f"{fname}: 한도 {max_bytes // (1024 * 1024)}MB 초과 (업로드 중단)"
                )
                continue
            try:
                meta = await sso_drive.upload_file(
                    day_folder_id,
                    fname,
                    data,
                    content_type=f.content_type or "application/octet-stream",
                )
                attachments_meta.append(
                    {
                        "drive_file_id": meta.get("fileId", ""),
                        "name": meta.get("fileName") or fname,
                        "size": int(meta.get("fileSize") or len(data)),
                        "type": f.content_type or "application/octet-stream",
                    }
                )
            except sso_drive.DriveError as exc:
                failed.append(f"{fname}: {exc}")

    # 5) 첨부메타 + 폴더 URL + 비고(실패 기록) update
    update_props: dict[str, Any] = {
        "첨부메타": {
            "rich_text": [
                {"text": {"content": _attachments_to_meta_json(attachments_meta)}}
            ]
        },
    }
    if folder_url:
        update_props["첨부폴더URL"] = {"url": folder_url}
    if failed:
        fail_note = "\n[업로드 실패]\n" + "\n".join(f" - {x}" for x in failed)
        update_props["비고"] = {
            "rich_text": [{"text": {"content": (note or "") + fail_note}}]
        }
    # PR-CA: notion update 최종 실패 시 partial_errors로 노출.
    try:
        await notion.update_page(page_id, update_props)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "seal_request 첨부메타 노션 update 실패 — Drive 파일은 존재 (page=%s)",
            page_id,
        )
        failed.append(f"노션 첨부메타 업데이트 실패: {exc}")

    # 6) 자동 TASK 생성 — fire-and-forget. 요청자 + 1차 검토자.
    _spawn_task(
        _create_seal_task_bg(
            notion,
            seal_page_id=page_id,
            seal_link_prop="연결TASK",
            project_id=project_id,
            title=f"[날인요청] {auto_title}",
            assignee_name=requester,
            today_iso=today_iso,
        )
    )
    # 1차 검토자 결정 — member 요청자면 같은 팀 팀장, 팀장이 없으면 admin 1명
    lead_reviewer_name = ""
    if user.role == "member":
        lead = _find_team_lead(db, requester_name=requester)
        if lead:
            lead_reviewer_name = lead.name or ""
        else:
            admins = _find_admins(db)
            if admins:
                lead_reviewer_name = admins[0].name or ""
    else:
        # team_lead 또는 admin이 직접 요청 → 1차는 admin 1명이 처리
        admins = _find_admins(db)
        if admins:
            lead_reviewer_name = admins[0].name or ""
    _spawn_task(
        _create_seal_task_bg(
            notion,
            seal_page_id=page_id,
            seal_link_prop="1차검토TASK",
            project_id=project_id,
            title=f"[날인 1차검토] {auto_title}",
            assignee_name=lead_reviewer_name,
            today_iso=today_iso,
        )
    )

    # 7) Bot 알림
    project_label = f"[{code}] {project_name}".strip("[] ") or project_name or project_id
    msg = (
        f"[날인요청] {project_label} - {seal_type} ({auto_title})"
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

    # 응답 — 자동 TASK는 background라 페이지에 아직 미반영. final fetch는 첨부메타/
    # 폴더URL 변경분을 정확한 read 형식으로 가져오기 위해 한 번만 호출.
    final = await notion.get_page(page_id)
    # PR-CQ: mirror_seal_requests 즉시 sync (5분 cron lag 회피).
    get_sync().upsert_page("seal_requests", final)
    item = _from_notion_page(final)
    # PR-BX/CA: failed[](텍스트) → partial_errors(정형) 분류.
    item.partial_errors = [_failed_to_partial(msg) for msg in failed]
    return item
