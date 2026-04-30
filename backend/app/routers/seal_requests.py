"""날인요청 라우터 — 검토구분 6종 + Works Drive 첨부 + 2단계 승인 + Bot 알림 + TASK 연동.

흐름 (docs/request.md):
    [작성] 사용자 (상태=1차검토 중) — 자동 TASK row 1건 생성 + 팀장에게 Bot 알림
       ↓
    [1차] 팀장/관리자 승인 (상태=2차검토 중) — admin들에게 Bot 알림
       ↓
    [최종] 관리자 승인 (상태=승인) — 요청자에게 Bot 알림 + TASK 진행 단계='완료'
       ↘ 반려 (상태=반려, 반려사유 별도 컬럼) — 요청자에게 Bot 알림

저장소: NAVER WORKS Drive 전용 — `[CODE]프로젝트명/0. 검토자료/YYYYMMDD/`.
        기존 S3 첨부는 다운/프리뷰만 호환 유지 (storage_key 보존).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
from app.models.auth import User
from app.models.employee import Employee
from app.security import get_current_user, require_admin, require_admin_or_lead
from app.services import file_storage as storage
from app.services import notion_props as P
from app.services import seal_logic as SL
from app.services import sso_drive
from app.services import sso_works_bot
from app.services.notion import NotionService, get_notion
from app.settings import get_settings

logger = logging.getLogger("seal_requests")

router = APIRouter(prefix="/seal-requests", tags=["seal-requests"])

# Bot send_text fire-and-forget 강 참조 set — GC가 task를 회수하기 전에 끝나도록 보관
_bg_tasks: set[asyncio.Task[Any]] = set()


def _max_bytes() -> int:
    return get_settings().storage_max_file_mb * 1024 * 1024


async def _read_with_limit(f: UploadFile, max_bytes: int) -> bytes | None:
    """`UploadFile`을 chunk 단위로 읽고 max_bytes 초과 시 즉시 중단 + None 반환.

    `await f.read()`로 통째 로드하면 큰 파일에서 단일 worker 메모리가 폭증하고
    Render starter plan에서 OOM/timeout으로 worker가 죽으며 502 cascade 발생.
    1MB chunk로 누적하면서 한도 초과 즉시 stop.
    """
    chunks: list[bytes] = []
    total = 0
    chunk_size = 1024 * 1024
    while True:
        chunk = await f.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


# ── 응답 스키마 ──


class SealAttachment(BaseModel):
    name: str
    # 다운로드 우선순위: drive_file_id(신규) → storage_key(legacy S3) → legacy_url(노션 files)
    drive_file_id: str = ""
    storage_key: str = ""
    legacy_url: str = ""
    size: int = 0
    content_type: str = ""


class SealRequestItem(BaseModel):
    id: str
    title: str = ""
    project_ids: list[str] = []
    seal_type: str = ""
    status: str = "1차검토 중"
    requester: str = ""
    lead_handler: str = ""
    admin_handler: str = ""
    requested_at: str | None = None
    lead_handled_at: str | None = None
    admin_handled_at: str | None = None
    due_date: str | None = None
    note: str = ""
    attachments: list[SealAttachment] = []
    # ── docs/request.md 추가 컬럼 ──
    real_source: str = ""        # 실제출처
    purpose: str = ""            # 용도
    revision: int | None = None  # Revision (구조계산서)
    with_safety_cert: bool = False  # 안전확인서포함 (구조계산서)
    summary: str = ""            # 내용요약 (구조검토서)
    doc_no: str = ""             # 문서번호 (구조검토서: YY-의견-NNN)
    doc_kind: str = ""           # 문서종류 (기타)
    folder_url: str = ""         # 첨부폴더URL (Works Drive 일자 폴더)
    reject_reason: str = ""      # 반려사유
    linked_task_id: str = ""     # 연결TASK page_id
    created_time: str | None = None
    last_edited_time: str | None = None


class SealListResponse(BaseModel):
    items: list[SealRequestItem]
    count: int


class PendingCount(BaseModel):
    count: int


class RejectBody(BaseModel):
    reason: str = ""


class SealUpdateBody(BaseModel):
    """재요청 시 텍스트 필드 일괄 수정.

    None인 필드는 변경 안 함. 빈 문자열은 'clear' 신호.
    """

    title: str | None = None
    real_source: str | None = None
    purpose: str | None = None
    revision: int | None = None
    with_safety_cert: bool | None = None
    summary: str | None = None
    doc_kind: str | None = None
    note: str | None = None
    due_date: str | None = None


# ── helper ──


def _parse_attachments_meta(props: dict[str, Any]) -> list[SealAttachment]:
    """첨부메타 rich_text 컬럼의 JSON 파싱.

    각 항목 schema:
        {"key": str(legacy S3), "drive_file_id": str(신규),
         "name": str, "size": int, "type": str}
    """
    raw = P.rich_text(props, "첨부메타")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
        out: list[SealAttachment] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            out.append(
                SealAttachment(
                    name=str(it.get("name", "")),
                    drive_file_id=str(it.get("drive_file_id", "")),
                    storage_key=str(it.get("key", "")),
                    size=int(it.get("size", 0) or 0),
                    content_type=str(it.get("type", "")),
                )
            )
        return out
    except (ValueError, TypeError):
        return []


def _attachments_to_meta_json(attachments: list[dict[str, Any]]) -> str:
    return json.dumps(attachments, ensure_ascii=False)


def _from_notion_page(page: dict[str, Any]) -> SealRequestItem:
    props = page.get("properties", {})
    s, _ = P.date_range(props, "요청일")
    lead_s, _ = P.date_range(props, "팀장처리일")
    admin_s, _ = P.date_range(props, "관리자처리일")
    due_s, _ = P.date_range(props, "제출예정일")

    attachments = _parse_attachments_meta(props)
    if not attachments:
        attachments = [
            SealAttachment(name=f["name"], legacy_url=f["url"])
            for f in P.files(props, "첨부파일")
        ]

    raw_type = P.select_name(props, "날인유형")
    raw_status = P.select_name(props, "상태")
    rev_n = P.number(props, "Revision")
    return SealRequestItem(
        id=page.get("id", ""),
        title=P.title(props, "제목"),
        project_ids=P.relation_ids(props, "프로젝트"),
        seal_type=SL.normalize_type(raw_type),
        status=SL.normalize_status(raw_status) or "1차검토 중",
        requester=P.rich_text(props, "요청자"),
        lead_handler=P.rich_text(props, "팀장처리자"),
        admin_handler=P.rich_text(props, "관리자처리자"),
        requested_at=s,
        lead_handled_at=lead_s,
        admin_handled_at=admin_s,
        due_date=due_s,
        note=P.rich_text(props, "비고"),
        attachments=attachments,
        real_source=P.rich_text(props, "실제출처"),
        purpose=P.rich_text(props, "용도"),
        revision=int(rev_n) if isinstance(rev_n, int | float) else None,
        with_safety_cert=P.checkbox(props, "안전확인서포함"),
        summary=P.rich_text(props, "내용요약"),
        doc_no=P.rich_text(props, "문서번호"),
        doc_kind=P.rich_text(props, "문서종류"),
        folder_url=P.url(props, "첨부폴더URL"),
        reject_reason=P.rich_text(props, "반려사유"),
        linked_task_id=P.rich_text(props, "연결TASK"),
        created_time=page.get("created_time"),
        last_edited_time=page.get("last_edited_time"),
    )


def _db_id() -> str:
    db_id = get_settings().notion_db_seal_requests
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_SEAL_REQUESTS 미설정",
        )
    return db_id


def _extract_resource_key(drive_url: str) -> str:
    """drive_url의 query string에서 resourceKey(=root folder fileId) 추출."""
    if not drive_url:
        return ""
    try:
        qs = parse_qs(urlparse(drive_url).query)
    except Exception:  # noqa: BLE001
        return ""
    v = qs.get("resourceKey")
    return v[0] if v else ""


def _can_access(user: User, page: dict[str, Any], db: Session) -> bool:
    if user.role in {"admin", "team_lead"}:
        return True
    me = user.name or ""
    if not me:
        return False
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자")
    if me == requester:
        return True
    project_ids = P.relation_ids(props, "프로젝트")
    if not project_ids:
        return False
    rows = db.execute(
        select(M.MirrorProject.assignees, M.MirrorProject.teams).where(
            M.MirrorProject.page_id.in_(project_ids)
        )
    ).all()
    for assignees, _teams in rows:
        if me in (assignees or []):
            return True
    return False


def _filter_accessible(
    user: User, pages: list[dict[str, Any]], db: Session
) -> list[dict[str, Any]]:
    if user.role in {"admin", "team_lead"}:
        return pages
    me = user.name or ""
    if not me:
        return []
    all_project_ids: set[str] = set()
    for p in pages:
        for pid in P.relation_ids(p.get("properties", {}), "프로젝트"):
            all_project_ids.add(pid)
    project_assignees: dict[str, list[str]] = {}
    if all_project_ids:
        rows = db.execute(
            select(M.MirrorProject.page_id, M.MirrorProject.assignees).where(
                M.MirrorProject.page_id.in_(all_project_ids)
            )
        ).all()
        project_assignees = {pid: (assigns or []) for pid, assigns in rows}

    out: list[dict[str, Any]] = []
    for p in pages:
        props = p.get("properties", {})
        if me == P.rich_text(props, "요청자"):
            out.append(p)
            continue
        for pid in P.relation_ids(props, "프로젝트"):
            if me in project_assignees.get(pid, []):
                out.append(p)
                break
    return out


# ── Bot 알림 ──


def _bot_send(user_id: str, text: str) -> None:
    """fire-and-forget 패턴 — 호출자 트랜잭션에 영향 주지 않음."""
    if not user_id:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(sso_works_bot.send_text(user_id, text))
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


def _resolve_works_id(u: User | None) -> str:
    """User에서 NAVER WORKS Bot 메시지 수신자 ID. works_user_id 우선, 없으면 email."""
    if u is None:
        return ""
    return (u.works_user_id or "") or (u.email or "")


def _find_team_lead(db: Session, *, requester_name: str) -> User | None:
    """요청자(이름)의 팀에 속한 team_lead 사용자 1명. 없으면 None.

    매핑 경로: requester_name → Employee.team → 같은 team의 Employee 중 team_lead
    role을 가진 User로 연결된 행 → User. linked_user_id가 비었으면 name으로 fallback.
    """
    if not requester_name:
        return None
    emp = db.execute(
        select(Employee).where(Employee.name == requester_name)
    ).scalar_one_or_none()
    team = (emp.team if emp else "") or ""
    if not team:
        return None
    candidates = db.execute(
        select(Employee).where(Employee.team == team, Employee.resigned_at.is_(None))
    ).scalars().all()
    for cand in candidates:
        if cand.name == requester_name:
            continue
        u: User | None = None
        if cand.linked_user_id:
            u = db.get(User, cand.linked_user_id)
        if u is None and cand.name:
            u = db.execute(
                select(User).where(User.name == cand.name, User.status == "active")
            ).scalar_one_or_none()
        if u and u.role == "team_lead":
            return u
    return None


def _find_admins(db: Session, *, exclude_user_id: int | None = None) -> list[User]:
    q = select(User).where(User.role == "admin", User.status == "active")
    if exclude_user_id is not None:
        q = q.where(User.id != exclude_user_id)
    return list(db.execute(q).scalars().all())


def _find_user_by_name(db: Session, name: str) -> User | None:
    if not name:
        return None
    return db.execute(
        select(User).where(User.name == name, User.status == "active")
    ).scalar_one_or_none()


# ── 자동 TASK 생성 / 동기화 ──


def _project_summary_from_db(
    db: Session, project_id: str
) -> tuple[str, str, str, str]:
    """(code, name, drive_url, root_folder_id) — drive_url은 mirror.properties 우선,
    없으면 빈 문자열."""
    row = db.get(M.MirrorProject, project_id)
    if row is None:
        return "", "", "", ""
    code = row.code or ""
    name = row.name or ""
    # mirror_projects의 properties JSONB에서 'WORKS Drive URL' 추출
    drive_url = ""
    try:
        url_prop = (row.properties or {}).get("WORKS Drive URL", {})
        if isinstance(url_prop, dict):
            v = url_prop.get("url")
            if isinstance(v, str):
                drive_url = v.replace("/share/root-folder?", "/share/folder?")
    except Exception:  # noqa: BLE001
        pass
    return code, name, drive_url, _extract_resource_key(drive_url)


async def _create_linked_task_bg(
    notion: NotionService,
    *,
    seal_page_id: str,
    project_id: str,
    title: str,
    requester_name: str,
    today_iso: str,
    due_iso: str,
) -> None:
    """노션 TASK DB row 생성 + SealRequest의 연결TASK 컬럼 update.

    response 흐름과 분리된 background — 실패해도 사용자 등록은 완료되어 있음.
    노션 task DB schema 미스, 노션 API timeout 등이 endpoint 응답을 막지 않게
    fire-and-forget으로 호출.
    """
    s = get_settings()
    if not s.notion_db_tasks:
        logger.warning("notion_db_tasks 미설정 — 자동 task 생성 skip")
        return
    props: dict[str, Any] = {
        "제목": {"title": [{"text": {"content": title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "분류": {"select": {"name": "프로젝트"}},
        "진행 단계": {"select": {"name": "진행 중"}},
        "기간": {"date": {"start": today_iso, "end": due_iso}},
    }
    if requester_name:
        props["담당자"] = {"multi_select": [{"name": requester_name}]}
    try:
        page = await notion.create_page(s.notion_db_tasks, props)
        task_id = str(page.get("id", ""))
        if task_id:
            await notion.update_page(
                seal_page_id,
                {"연결TASK": {"rich_text": [{"text": {"content": task_id}}]}},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("자동 task 생성/연결 실패: %s", e)


async def _sync_linked_task(
    notion: NotionService, task_id: str, *, target: str
) -> None:
    """target ∈ {'완료', '취소'}. '완료'는 진행 단계 update, '취소'는 archive."""
    if not task_id:
        return
    try:
        if target == "취소":
            await asyncio.to_thread(
                notion._client.pages.update, page_id=task_id, archived=True
            )
        else:
            await notion.update_page(
                task_id, {"진행 단계": {"select": {"name": target}}}
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("연결 task 동기화 실패 (%s, %s): %s", task_id, target, e)


# ── endpoints ──


@router.get("", response_model=SealListResponse)
async def list_seal_requests(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealListResponse:
    """날인요청 목록.

    docs/request.md: 일반직원은 날인요청 페이지 접근 불가. 단 프로젝트 상세에서
    `project_id` 필터로 자신의 프로젝트 진행 상황은 확인 가능 — 이 경우는 허용.
    """
    if user.role not in {"admin", "team_lead"} and not project_id:
        raise HTTPException(
            status_code=403,
            detail="일반직원은 날인요청 페이지를 직접 조회할 수 없습니다",
        )
    pages = await notion.query_all(
        _db_id(),
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    if project_id:
        pages = [
            p
            for p in pages
            if project_id
            in P.relation_ids(p.get("properties", {}), "프로젝트")
        ]
    pages = _filter_accessible(user, pages, db)
    items = [_from_notion_page(p) for p in pages]
    return SealListResponse(items=items, count=len(items))


@router.get("/pending-count", response_model=PendingCount)
async def get_pending_count(
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> PendingCount:
    """본인이 처리해야 할 건수 (사이드바 알림 배지용).

    - team_lead: '1차검토 중'(또는 호환 '요청')
    - admin: '2차검토 중'(또는 호환 '팀장승인')
    """
    if user.role == "team_lead":
        targets = ["1차검토 중", "요청"]
    elif user.role == "admin":
        targets = ["2차검토 중", "팀장승인"]
    else:
        return PendingCount(count=0)
    pages = await notion.query_all(
        _db_id(),
        filter={
            "or": [
                {"property": "상태", "select": {"equals": t}} for t in targets
            ]
        },
    )
    return PendingCount(count=len(pages))


@router.post("", response_model=SealRequestItem, status_code=status.HTTP_201_CREATED)
async def create_seal_request(
    project_id: str = Form(..., description="노션 프로젝트 page_id"),
    seal_type: str = Form(..., description="구조계산서/구조안전확인서/구조검토서/구조도면/보고서/기타"),
    due_date: str = Form(..., description="제출 예정일 (YYYY-MM-DD, 필수)"),
    title: str = Form("", description="제목 (생략 시 자동 생성)"),
    note: str = Form(""),
    real_source: str = Form("", description="실제출처 (발주처와 다른 경우만)"),
    purpose: str = Form("", description="용도 — 구조계산서/구조안전확인서/구조도면"),
    revision: int = Form(0, description="Revision — 구조계산서"),
    with_safety_cert: bool = Form(False, description="안전확인서포함 — 구조계산서"),
    summary: str = Form("", description="내용요약 — 구조검토서"),
    doc_kind: str = Form("", description="문서종류 — 기타"),
    files: list[UploadFile] = File([], description="첨부 파일 (선택, 다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
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
    init_props: dict[str, Any] = {
        "제목": {"title": [{"text": {"content": auto_title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "날인유형": {"select": {"name": seal_type}},
        "상태": {"select": {"name": "1차검토 중"}},
        "요청자": {"rich_text": [{"text": {"content": requester}}]},
        "요청일": {"date": {"start": today_iso}},
        "제출예정일": {"date": {"start": due_iso}},
        "비고": {"rich_text": [{"text": {"content": note}}]},
    }
    if real_source.strip():
        init_props["실제출처"] = {
            "rich_text": [{"text": {"content": real_source.strip()}}]
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

    # 4) 첨부파일 업로드 → Works Drive (`0. 검토자료/YYYYMMDD/`)
    attachments_meta: list[dict[str, Any]] = []
    failed: list[str] = []
    folder_url = ""
    if files:
        s_set = get_settings()
        if not s_set.works_drive_enabled or not root_folder_id:
            failed.extend(
                [f"{(f.filename or 'file.bin')}: Drive 미연결" for f in files]
            )
        else:
            ymd = today.strftime("%Y%m%d")
            try:
                day_folder_id, day_folder_url = await sso_drive.ensure_review_folder(
                    root_folder_id, ymd
                )
                folder_url = day_folder_url
            except sso_drive.DriveError as exc:
                logger.warning("검토자료 폴더 생성 실패: %s", exc)
                day_folder_id = ""
                failed.extend(
                    [f"{(f.filename or 'file.bin')}: 폴더 생성 실패 ({exc})" for f in files]
                )
            if day_folder_id:
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
    await notion.update_page(page_id, update_props)

    # 6) 자동 TASK 생성 — fire-and-forget. 노션 task DB schema 미스 또는 노션 API
    #    timeout이 endpoint 응답을 막지 않게 background로 분리. 실패는 logger warn.
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(
            _create_linked_task_bg(
                notion,
                seal_page_id=page_id,
                project_id=project_id,
                title=auto_title,
                requester_name=requester,
                today_iso=today_iso,
                due_iso=due_iso,
            )
        )
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    except RuntimeError:
        pass  # 테스트 컨텍스트 등 — silent skip

    # 7) Bot 알림 — 1차 처리자(팀장 또는 admin)에게
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
        # team_lead 또는 admin이 직접 요청 → admin 전원(본인 외)
        for adm in _find_admins(db, exclude_user_id=user.id):
            _bot_send(_resolve_works_id(adm), msg)

    # 응답 — 자동 TASK는 background라 페이지에 아직 미반영. final fetch는 첨부메타/
    # 폴더URL 변경분을 정확한 read 형식으로 가져오기 위해 한 번만 호출.
    final = await notion.get_page(page_id)
    return _from_notion_page(final)


async def _set_status_with_handler(
    notion: NotionService,
    page_id: str,
    new_status: str,
    handler_field: str,
    handler_date_field: str,
    handler_name: str,
) -> dict[str, Any]:
    today = date.today().isoformat()
    return await notion.update_page(
        page_id,
        {
            "상태": {"select": {"name": new_status}},
            handler_field: {"rich_text": [{"text": {"content": handler_name}}]},
            handler_date_field: {"date": {"start": today}},
        },
    )


@router.patch("/{page_id}/approve-lead", response_model=SealRequestItem)
async def approve_lead(
    page_id: str,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur != "1차검토 중":
        raise HTTPException(
            status_code=400,
            detail=f"현재 상태가 '1차검토 중'이 아닙니다 (현재: {cur or '미정'})",
        )
    handler = user.name or user.username
    await _set_status_with_handler(
        notion, page_id, "2차검토 중", "팀장처리자", "팀장처리일", handler
    )

    # Bot 알림 — admin들에게 (본인 admin이면 본인 제외)
    item = _from_notion_page(page)
    msg = (
        f"[2차검토 요청] {item.title}"
        f"\n1차검토자: {handler} / 요청자: {item.requester} / 제출예정일: {item.due_date or '-'}"
    )
    for adm in _find_admins(db, exclude_user_id=user.id if user.role == "admin" else None):
        _bot_send(_resolve_works_id(adm), msg)

    updated = await notion.get_page(page_id)
    return _from_notion_page(updated)


@router.patch("/{page_id}/approve-admin", response_model=SealRequestItem)
async def approve_admin(
    page_id: str,
    user: User = Depends(require_admin),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur not in {"2차검토 중", "1차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"승인 가능 상태가 아님 (현재: {cur or '미정'})",
        )
    handler = user.name or user.username
    await _set_status_with_handler(
        notion, page_id, "승인", "관리자처리자", "관리자처리일", handler
    )

    item = _from_notion_page(page)
    # 연결 task → 진행 단계 '완료'
    if item.linked_task_id:
        await _sync_linked_task(notion, item.linked_task_id, target="완료")

    # Bot 알림 — 요청자에게
    requester_user = _find_user_by_name(db, item.requester)
    msg = (
        f"[승인 완료] {item.title}\n처리자: {handler}"
    )
    _bot_send(_resolve_works_id(requester_user), msg)

    updated = await notion.get_page(page_id)
    return _from_notion_page(updated)


@router.patch("/{page_id}/reject", response_model=SealRequestItem)
async def reject_seal_request(
    page_id: str,
    body: RejectBody,
    user: User = Depends(require_admin_or_lead),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    cur = SL.normalize_status(P.select_name(page.get("properties", {}), "상태"))
    if cur not in {"1차검토 중", "2차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"반려 가능 상태가 아님 (현재: {cur or '미정'})",
        )
    rejector = user.name or user.username
    reason = (body.reason or "").strip()
    update_props: dict[str, Any] = {
        "상태": {"select": {"name": "반려"}},
        "반려사유": {
            "rich_text": [
                {"text": {"content": f"[{rejector}] {reason}" if reason else f"[{rejector}]"}}
            ]
        },
    }
    await notion.update_page(page_id, update_props)

    item = _from_notion_page(page)
    requester_user = _find_user_by_name(db, item.requester)
    msg = (
        f"[반려] {item.title}"
        f"\n사유: {reason or '(미기재)'} / 처리자: {rejector}"
    )
    _bot_send(_resolve_works_id(requester_user), msg)

    updated = await notion.get_page(page_id)
    return _from_notion_page(updated)


@router.patch("/{page_id}", response_model=SealRequestItem)
async def update_seal_request(
    page_id: str,
    body: SealUpdateBody,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    """재요청용 텍스트 필드 update. 본인 또는 admin/team_lead만,
    상태가 '반려' 또는 '1차검토 중'(아직 처리 전)일 때만 허용.
    상태가 '반려'였으면 '1차검토 중'으로 복구 + Bot 알림 재발송.
    """
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
        update_props["제목"] = {"title": [{"text": {"content": body.title}}]}
    if body.real_source is not None:
        update_props["실제출처"] = {
            "rich_text": [{"text": {"content": body.real_source}}]
        }
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

    # 반려 → 재요청이면 알림 재발송
    if cur_status == "반려":
        item = _from_notion_page(page)
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
            for adm in _find_admins(db, exclude_user_id=user.id):
                _bot_send(_resolve_works_id(adm), msg)

    updated = await notion.get_page(page_id)
    return _from_notion_page(updated)


def _get_attachment_or_404(
    page: dict[str, Any], idx: int
) -> SealAttachment:
    props = page.get("properties", {})
    items = _parse_attachments_meta(props)
    if not items:
        items = [
            SealAttachment(name=f["name"], legacy_url=f["url"])
            for f in P.files(props, "첨부파일")
        ]
    if idx < 0 or idx >= len(items):
        raise HTTPException(status_code=404, detail="첨부파일을 찾을 수 없습니다")
    return items[idx]


@router.get("/{page_id}/download/{idx}")
async def get_attachment_url(
    page_id: str,
    idx: int,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)
    # 우선순위: drive_file_id → storage_key → legacy_url
    if item.drive_file_id:
        try:
            url = await sso_drive.get_download_url(item.drive_file_id)
        except sso_drive.DriveError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"url": url, "name": item.name}
    if item.storage_key:
        try:
            url = storage.presigned_get_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"url": url, "name": item.name}
    return {"url": item.legacy_url, "name": item.name}


@router.get("/{page_id}/preview/{idx}")
async def preview_attachment(
    page_id: str,
    idx: int,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
):
    """stream proxy + Content-Disposition: inline."""
    import httpx
    from fastapi.responses import StreamingResponse

    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    item = _get_attachment_or_404(page, idx)

    if item.drive_file_id:
        try:
            url = await sso_drive.get_download_url(item.drive_file_id)
        except sso_drive.DriveError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    elif item.storage_key:
        try:
            url = storage.presigned_inline_url(
                key=item.storage_key, filename=item.name
            )
        except storage.StorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    else:
        url = item.legacy_url
    filename = item.name or "file.bin"

    client = httpx.AsyncClient(timeout=120.0)
    try:
        upstream = await client.send(
            client.build_request("GET", url), stream=True
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502, detail=f"파일 fetch 실패: {exc}"
        ) from exc
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=upstream.status_code, detail="파일 fetch 실패"
        )

    media_type = upstream.headers.get(
        "content-type", item.content_type or "application/octet-stream"
    )

    async def _iter():
        try:
            async for chunk in upstream.aiter_bytes(chunk_size=64 * 1024):
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _iter(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/{page_id}/attachments", response_model=SealRequestItem)
async def add_attachments(
    page_id: str,
    files: list[UploadFile] = File(..., description="추가 첨부파일 (다중 가능)"),
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    """반려된 요청을 보완해 파일을 추가하면서 상태를 '1차검토 중'으로 되돌림.

    권한: 작성자 본인 또는 admin/team_lead.
    상태: '반려' 또는 '1차검토 중'(legacy '요청') 일 때만.
    """
    if not files:
        raise HTTPException(status_code=400, detail="추가할 파일을 선택하세요")
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    props = page.get("properties", {})
    cur_status = SL.normalize_status(P.select_name(props, "상태"))
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    is_lead_admin = user.role in {"admin", "team_lead"}
    if not (is_owner or is_lead_admin):
        raise HTTPException(
            status_code=403, detail="본인 요청만 보완 업로드 가능"
        )
    if cur_status not in {"반려", "1차검토 중"}:
        raise HTTPException(
            status_code=400,
            detail=f"'{cur_status}' 상태에서는 재업로드 불가 (반려 또는 1차검토 중에서만)",
        )

    # 프로젝트 root 폴더 → 일자 폴더
    project_ids = P.relation_ids(props, "프로젝트")
    project_id = project_ids[0] if project_ids else ""
    _code, _name, _drive_url, root_folder_id = _project_summary_from_db(
        db, project_id
    )
    s_set = get_settings()
    today = date.today()
    today_iso = today.isoformat()
    ymd = today.strftime("%Y%m%d")

    existing_meta = _parse_attachments_meta(props)
    new_meta = [
        {
            "drive_file_id": a.drive_file_id,
            "key": a.storage_key,
            "name": a.name,
            "size": a.size,
            "type": a.content_type,
        }
        for a in existing_meta
        if (a.drive_file_id or a.storage_key)
    ]

    max_bytes = _max_bytes()
    failed: list[str] = []
    folder_url = ""
    if not s_set.works_drive_enabled or not root_folder_id:
        failed.extend(
            [f"{(f.filename or 'file.bin')}: Drive 미연결" for f in files]
        )
    else:
        try:
            day_folder_id, day_folder_url = await sso_drive.ensure_review_folder(
                root_folder_id, ymd
            )
            folder_url = day_folder_url
        except sso_drive.DriveError as exc:
            day_folder_id = ""
            failed.extend(
                [f"{(f.filename or 'file.bin')}: 폴더 생성 실패 ({exc})" for f in files]
            )
        if day_folder_id:
            for f in files:
                data = await f.read()
                fname = f.filename or "file.bin"
                if len(data) > max_bytes:
                    failed.append(
                        f"{fname}: 한도 {max_bytes // (1024 * 1024)}MB 초과"
                    )
                    continue
                try:
                    meta = await sso_drive.upload_file(
                        day_folder_id,
                        fname,
                        data,
                        content_type=f.content_type or "application/octet-stream",
                    )
                    new_meta.append(
                        {
                            "drive_file_id": meta.get("fileId", ""),
                            "name": meta.get("fileName") or fname,
                            "size": int(meta.get("fileSize") or len(data)),
                            "type": f.content_type or "application/octet-stream",
                        }
                    )
                except sso_drive.DriveError as exc:
                    failed.append(f"{fname}: {exc}")

    update_props: dict[str, Any] = {
        "첨부메타": {
            "rich_text": [
                {"text": {"content": _attachments_to_meta_json(new_meta)}}
            ]
        },
        "상태": {"select": {"name": "1차검토 중"}},
    }
    if folder_url:
        update_props["첨부폴더URL"] = {"url": folder_url}
    if cur_status == "반려":
        existing_note = P.rich_text(props, "비고")
        actor = user.name or user.username
        new_note = (
            f"{existing_note}\n[재제출 by {actor} {today_iso}] 파일 {len(files)}개 보완"
            if existing_note
            else f"[재제출 by {actor} {today_iso}] 파일 {len(files)}개 보완"
        )
        update_props["비고"] = {"rich_text": [{"text": {"content": new_note}}]}
        update_props["팀장처리자"] = {"rich_text": [{"text": {"content": ""}}]}
        update_props["팀장처리일"] = {"date": None}

    await notion.update_page(page_id, update_props)
    if failed:
        logger.warning("첨부 추가 일부 실패 (page=%s): %s", page_id, failed)
    final = await notion.get_page(page_id)
    return _from_notion_page(final)


@router.delete("/{page_id}")
async def delete_seal_request(
    page_id: str,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """취소 — 작성자 본인 또는 admin.

    구조검토서이며 문서번호가 발급되어 있으면:
        - 후속 번호가 이미 있음(중간 번호)  → archive 안 함, 제목 [날인취소] prefix + 상태 '반려'
        - 후속 번호 없음(마지막 번호)        → archive (다음 발급에서 그 번호 회수)
    그 외 유형: archive.
    """
    try:
        page = await notion.get_page(page_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    if not _can_access(user, page, db):
        raise HTTPException(status_code=403, detail="해당 요청 접근 권한이 없습니다")
    props = page.get("properties", {})
    requester = P.rich_text(props, "요청자")
    is_owner = (user.name or user.username) == requester
    if not (is_owner or user.role == "admin"):
        raise HTTPException(
            status_code=403, detail="본인 글만 삭제 가능 (관리자는 모두 가능)"
        )

    seal_type = SL.normalize_type(P.select_name(props, "날인유형"))
    doc_no = P.rich_text(props, "문서번호").strip()
    keep_with_marker = False
    if seal_type == "구조검토서" and doc_no:
        try:
            is_last = await SL.is_last_review_doc_number(
                notion, _db_id(), doc_no=doc_no
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("마지막 번호 검사 실패: %s — 보수적으로 흔적 남김", e)
            is_last = False
        keep_with_marker = not is_last

    item = _from_notion_page(page)

    if keep_with_marker:
        # 흔적 남김: 제목 prefix + 상태 '취소' (재요청 차단) + 첨부메타 비움
        cur_title = P.title(props, "제목")
        new_title = (
            cur_title if cur_title.startswith("[날인취소] ") else f"[날인취소] {cur_title}"
        )
        await notion.update_page(
            page_id,
            {
                "제목": {"title": [{"text": {"content": new_title}}]},
                "상태": {"select": {"name": "취소"}},
                "반려사유": {
                    "rich_text": [
                        {"text": {"content": f"[취소 by {user.name or user.username}]"}}
                    ]
                },
                "첨부메타": {"rich_text": [{"text": {"content": "[]"}}]},
            },
        )
    else:
        # legacy S3 cleanup (있으면)
        for a in _parse_attachments_meta(props):
            if a.storage_key:
                try:
                    storage.delete_object(key=a.storage_key)
                except storage.StorageError as e:
                    logger.warning("S3 cleanup 실패 (%s): %s", a.storage_key, e)
        await asyncio.to_thread(
            notion._client.pages.update, page_id=page_id, archived=True
        )

    # 연결 task archive
    if item.linked_task_id:
        await _sync_linked_task(notion, item.linked_task_id, target="취소")

    notion.clear_cache()
    return {
        "status": "marked-cancelled" if keep_with_marker else "archived",
    }
