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
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("seal_requests")

router = APIRouter(prefix="/seal-requests", tags=["seal-requests"])

# PR-CG/CH (Phase 4-J): sub-router include는 파일 끝으로 — attachments.py가
# 이 모듈의 _can_access helper를 lazy import 하므로 fully loaded 후 mount.

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


# PR-BX (외부 리뷰 12.x #1 본격): 부분 실패 정형화. 기존 비고 텍스트 append와 병행.
# frontend는 응답에 partial_errors가 있으면 toast로 사용자 안내.
class PartialError(BaseModel):
    code: str          # 예: "drive_upload" / "drive_folder" / "notion_update"
    target: str = ""   # 실패 대상 식별자 (파일명, page_id 등)
    message: str = ""
    retryable: bool = True


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
    # 실제출처: 거래처 DB(notion_db_clients) relation. 단일 선택. 이름은 frontend가
    # useClients로 resolve.
    real_source_id: str = ""
    purpose: str = ""            # 용도
    revision: int | None = None  # Revision (구조계산서)
    with_safety_cert: bool = False  # 안전확인서포함 (구조계산서)
    summary: str = ""            # 내용요약 (구조검토서)
    doc_no: str = ""             # 문서번호 (구조검토서: YY-의견-NNN)
    doc_kind: str = ""           # 문서종류 (기타)
    folder_url: str = ""         # 첨부폴더URL (Works Drive 일자 폴더)
    reject_reason: str = ""      # 반려사유
    linked_task_id: str = ""     # 연결TASK page_id (요청자용)
    lead_task_id: str = ""       # 1차검토TASK page_id (팀장 또는 admin)
    admin_task_id: str = ""      # 2차검토TASK page_id (admin)
    created_time: str | None = None
    last_edited_time: str | None = None
    # PR-BX: 응답 시점에 발생한 부분 실패(Drive 업로드/폴더 생성 등). 기존 비고
    # 텍스트 append와 별도로 정형 응답. list endpoint 응답에는 항상 빈 list.
    partial_errors: list[PartialError] = []


class SealListResponse(BaseModel):
    items: list[SealRequestItem]
    count: int


# PendingCount — PR-CG에서 seal_requests/meta.py로 이동


class RejectBody(BaseModel):
    reason: str = ""


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
    real_source_ids = P.relation_ids(props, "실제출처")
    real_source_id = real_source_ids[0] if real_source_ids else ""
    # title prop은 DB마다 이름이 다를 수 있어 type='title'인 컬럼을 찾는다.
    title_text = ""
    for v in props.values():
        if isinstance(v, dict) and v.get("type") == "title":
            arr = v.get("title") or []
            title_text = arr[0].get("plain_text", "") if arr else ""
            break
    return SealRequestItem(
        id=page.get("id", ""),
        title=title_text,
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
        real_source_id=real_source_id,
        purpose=P.rich_text(props, "용도"),
        revision=int(rev_n) if isinstance(rev_n, int | float) else None,
        with_safety_cert=P.checkbox(props, "안전확인서포함"),
        summary=P.rich_text(props, "내용요약"),
        doc_no=P.rich_text(props, "문서번호"),
        doc_kind=P.rich_text(props, "문서종류"),
        folder_url=P.url(props, "첨부폴더URL"),
        reject_reason=P.rich_text(props, "반려사유"),
        linked_task_id=P.rich_text(props, "연결TASK"),
        lead_task_id=P.rich_text(props, "1차검토TASK"),
        admin_task_id=P.rich_text(props, "2차검토TASK"),
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


# title property 이름은 노션 DB마다 다를 수 있어(`제목`/`이름`/`Name` 등) 동적 탐지.
# 첫 호출 시 schema query → cache. 운영 중 변경되는 일은 거의 없으므로 process
# lifetime 동안 cache 유지.
_title_prop_name: str | None = None


async def _get_title_prop_name(notion: NotionService) -> str:
    """날인요청 DB의 title type property 이름. 첫 호출에 schema query, 이후 cache."""
    global _title_prop_name
    if _title_prop_name is not None:
        return _title_prop_name
    try:
        ds = await notion.get_data_source(_db_id())
    except Exception as e:  # noqa: BLE001
        logger.warning("title prop 탐지 실패 — `제목` fallback: %s", e)
        return "제목"
    for name, spec in (ds.get("properties") or {}).items():
        if isinstance(spec, dict) and spec.get("type") == "title":
            _title_prop_name = name
            return name
    logger.warning("날인요청 DB에 title type property 없음 — `제목` fallback")
    return "제목"


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
    if user.role == "admin":
        return pages
    if user.role == "team_lead":
        # 자기 팀의 진행 현황만 — 요청자가 같은 팀에 속한 직원이어야 함
        me = user.name or ""
        if not me:
            return []
        my_emp = db.execute(
            select(Employee).where(Employee.name == me)
        ).scalar_one_or_none()
        my_team = (my_emp.team if my_emp else "") or ""
        if not my_team:
            return []
        team_member_names = {
            row
            for row in db.execute(
                select(Employee.name).where(
                    Employee.team == my_team, Employee.resigned_at.is_(None)
                )
            ).scalars().all()
        }
        return [
            p
            for p in pages
            if P.rich_text(p.get("properties", {}), "요청자")
            in team_member_names
        ]
    # member — 본인 요청 또는 본인이 담당자로 등록된 프로젝트만
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


def _sort_items_by_role(
    items: list[SealRequestItem], role: str
) -> list[SealRequestItem]:
    """역할별 상태 우선순위 + 상태별 due_date 정렬.

    docs/request.md 정책:
    - admin: 2차검토 중 → 1차검토 중 → 반려 → 승인
    - team_lead: 1차검토 중 → 2차검토 중 → 반려 → 승인
    - 검토중/반려: due_date asc (제출예정일 가까운 것 우선)
    - 승인: due_date desc (최신 승인이 위)
    """
    if role == "admin":
        order = ["2차검토 중", "1차검토 중", "반려", "승인"]
    else:
        order = ["1차검토 중", "2차검토 중", "반려", "승인"]
    buckets: dict[str, list[SealRequestItem]] = {s: [] for s in order}
    misc: list[SealRequestItem] = []
    for it in items:
        if it.status in buckets:
            buckets[it.status].append(it)
        else:
            misc.append(it)
    out: list[SealRequestItem] = []
    for status in order:
        bucket = buckets[status]
        if status == "승인":
            bucket.sort(key=lambda x: x.due_date or "", reverse=True)
        else:
            # 빈 값은 가장 뒤로 (제출예정일 미정인 요청은 우선순위 마지막)
            bucket.sort(key=lambda x: x.due_date or "9999-99-99")
        out.extend(bucket)
    out.extend(misc)
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


async def _create_seal_task_bg(
    notion: NotionService,
    *,
    seal_page_id: str,
    seal_link_prop: str,
    project_id: str,
    title: str,
    assignee_name: str,
    today_iso: str,
) -> None:
    """노션 TASK DB row 생성 + SealRequest의 연결 컬럼(rich_text) update.

    docs/request.md 정책: 시작일=등록일/단계전환일, 완료일은 미정. 기간은 end
    없이 단일 날짜로 시작 → _sync_linked_task('완료')에서 end=오늘로 추가.

    seal_link_prop 예: "연결TASK"(요청자), "1차검토TASK"(팀장), "2차검토TASK"(admin).
    response와 분리된 fire-and-forget — 실패해도 사용자 흐름엔 영향 없음.
    """
    s = get_settings()
    if not s.notion_db_tasks:
        logger.warning("notion_db_tasks 미설정 — 자동 task 생성 skip (%s)", seal_link_prop)
        return
    if not assignee_name:
        logger.info("assignee 미지정 — task 생성 skip (%s)", seal_link_prop)
        return
    # 노션 task DB 실제 컬럼명: title="내용", status type="상태", select="분류".
    # task_create_to_props와 동일한 schema로 맞춰야 mirror 동기화·칸반 표시 정상.
    props: dict[str, Any] = {
        "내용": {"title": [{"text": {"content": title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "분류": {"select": {"name": "프로젝트"}},
        "상태": {"status": {"name": "진행 중"}},
        "기간": {"date": {"start": today_iso}},
        "담당자": {"multi_select": [{"name": assignee_name}]},
    }
    try:
        page = await notion.create_page(s.notion_db_tasks, props)
        task_id = str(page.get("id", ""))
        if task_id:
            # write-through — mirror_tasks에 즉시 upsert. 일반 task create와
            # 동일하게 5분 incremental sync 전에 프로젝트 칸반에 보이도록.
            try:
                get_sync().upsert_page("tasks", page)
            except Exception as e:  # noqa: BLE001
                logger.warning("자동 task mirror upsert 실패: %s", e)
            await notion.update_page(
                seal_page_id,
                {seal_link_prop: {"rich_text": [{"text": {"content": task_id}}]}},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("자동 task 생성/연결 실패 (%s): %s", seal_link_prop, e)


def _spawn_task(coro: Any) -> None:
    """fire-and-forget — bg_tasks set에 보관해 GC 회수 방지."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _sync_linked_task(
    notion: NotionService, task_id: str, *, target: str
) -> None:
    """target ∈ {'완료', '취소'}.

    '완료': 노션 task DB 실제 schema에 맞춰 status type '상태'='완료' + 기간.end
    =오늘. docs/request.md 정책으로 자동 task 완료일은 단계 마감일로 채움.
    '취소': 노션 페이지 archive.
    """
    if not task_id:
        return
    try:
        if target == "취소":
            await asyncio.to_thread(
                notion._client.pages.update, page_id=task_id, archived=True
            )
            return
        # 완료 — 기간.end를 채우려면 기존 start 값 보존 필요.
        try:
            cur = await notion.get_page(task_id)
            start = (
                (cur.get("properties", {}).get("기간") or {})
                .get("date", {})
                .get("start")
                or date.today().isoformat()
            )
        except Exception:  # noqa: BLE001
            start = date.today().isoformat()
        today_iso = date.today().isoformat()
        updated = await notion.update_page(
            task_id,
            {
                "상태": {"status": {"name": "완료"}},
                "기간": {"date": {"start": start, "end": today_iso}},
                "실제 완료일": {"date": {"start": today_iso}},
            },
        )
        # write-through — 5분 sync 전에 칸반에서 '진행 중' → '완료' 이동 즉시 반영
        try:
            get_sync().upsert_page("tasks", updated)
        except Exception as e:  # noqa: BLE001
            logger.warning("자동 task mirror upsert 실패 (완료): %s", e)
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
    items = _sort_items_by_role(items, user.role or "member")
    return SealListResponse(items=items, count=len(items))


# /next-doc-number + /pending-count + 2 model — PR-CG에서 seal_requests/meta.py로 분리


@router.post("", response_model=SealRequestItem, status_code=status.HTTP_201_CREATED)
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
    # backend 자동 ensure는 하지 않음 (사용자 의도: 명시 생성만). 못 찾으면 빈 채로 둠.
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
        # 폴더 미생성 상태에서 첨부가 들어온 경우만 사용자에게 알림
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
    # PR-CA (외부 리뷰 12.x #2): notion.update_page는 _call에서 4 attempts retry되지만
    # 그래도 최종 실패하면 raise → Drive에 orphan 파일 + 사용자 500. try/except로 wrap해
    # partial_errors로 노출 (사용자 알림 + 운영 수동 보정 단서).
    try:
        await notion.update_page(page_id, update_props)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "seal_request 첨부메타 노션 update 실패 — Drive 파일은 존재 (page=%s)",
            page_id,
        )
        failed.append(f"노션 첨부메타 업데이트 실패: {exc}")

    # 6) 자동 TASK 생성 — fire-and-forget.
    # 요청자용 1개 + 1차 검토자(팀장 또는 admin)용 1개.
    # 시작일=오늘, 완료일은 승인/반려 시점에 _sync_linked_task로 채움.
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
        # team_lead 또는 admin이 직접 요청 → admin 전원 (본인 포함)
        for adm in _find_admins(db):
            _bot_send(_resolve_works_id(adm), msg)

    # 응답 — 자동 TASK는 background라 페이지에 아직 미반영. final fetch는 첨부메타/
    # 폴더URL 변경분을 정확한 read 형식으로 가져오기 위해 한 번만 호출.
    final = await notion.get_page(page_id)
    item = _from_notion_page(final)
    # PR-BX: failed[](텍스트)를 partial_errors(정형)로도 응답. 비고에는 이미 append됨.
    # PR-CA: 노션 update 실패도 failed에 섞이므로 prefix로 code 분기.
    item.partial_errors = [_failed_to_partial(msg) for msg in failed]
    return item


def _failed_to_partial(msg: str) -> PartialError:
    """failed[] 텍스트를 PartialError로 분류. 노션 update 실패면 code='notion_update'."""
    if msg.startswith("노션 "):
        return PartialError(code="notion_update", target="page", message=msg)
    return PartialError(
        code="drive_upload", target=msg.split(":", 1)[0], message=msg
    )


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
    item = _from_notion_page(page)

    await _set_status_with_handler(
        notion, page_id, "2차검토 중", "팀장처리자", "팀장처리일", handler
    )

    # 1차 검토자 TASK 완료 + 2차 검토자(admin) TASK 생성
    if item.lead_task_id:
        await _sync_linked_task(notion, item.lead_task_id, target="완료")
    project_id_for_task = item.project_ids[0] if item.project_ids else ""
    admins = _find_admins(db)
    admin_reviewer_name = (admins[0].name or "") if admins else ""
    if project_id_for_task and admin_reviewer_name:
        _spawn_task(
            _create_seal_task_bg(
                notion,
                seal_page_id=page_id,
                seal_link_prop="2차검토TASK",
                project_id=project_id_for_task,
                title=f"[날인 2차검토] {item.title}",
                assignee_name=admin_reviewer_name,
                today_iso=date.today().isoformat(),
            )
        )

    # Bot 알림 — admin 전원 (본인 포함)
    msg = (
        f"[2차검토 요청] {item.title}"
        f"\n1차검토자: {handler} / 요청자: {item.requester} / 제출예정일: {item.due_date or '-'}"
    )
    for adm in _find_admins(db):
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
    item = _from_notion_page(page)

    await _set_status_with_handler(
        notion, page_id, "승인", "관리자처리자", "관리자처리일", handler
    )

    # 2차 검토자 TASK 완료 + (1차 검토자 TASK가 1차 미경유 케이스로 남아있으면 함께 완료)
    # + 요청자 TASK 완료
    if item.admin_task_id:
        await _sync_linked_task(notion, item.admin_task_id, target="완료")
    if item.lead_task_id:
        # 1차 미경유로 admin이 바로 승인한 경우 lead task가 진행 중일 수 있어 같이 완료
        await _sync_linked_task(notion, item.lead_task_id, target="완료")
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
    # 정책: 팀장은 1차검토 단계에서만 반려 가능. 2차검토 중인 항목의 반려는 admin only.
    if cur == "2차검토 중" and user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="2차검토 중인 항목의 반려는 관리자만 가능합니다",
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

    # 현재 단계 검토자 TASK 완료 (반려도 검토 완료로 간주). 요청자 TASK는
    # 그대로 진행 — 사용자가 재요청하면 다시 1차검토 중으로 돌아감.
    item_for_task = _from_notion_page(page)
    if cur == "1차검토 중" and item_for_task.lead_task_id:
        await _sync_linked_task(notion, item_for_task.lead_task_id, target="완료")
    elif cur == "2차검토 중" and item_for_task.admin_task_id:
        await _sync_linked_task(notion, item_for_task.admin_task_id, target="완료")

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


# _get_attachment_or_404 + GET /:id/download/:idx + GET /:id/preview/:idx —
# PR-CH에서 routers/seal_requests/attachments.py로 이동


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

    # PR-CA (외부 리뷰 12.x #2): notion update 최종 실패 시 partial_errors로 노출.
    try:
        await notion.update_page(page_id, update_props)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "seal_request 첨부 add 노션 update 실패 — Drive 파일은 존재 (page=%s)",
            page_id,
        )
        failed.append(f"노션 첨부메타 업데이트 실패: {exc}")
    if failed:
        logger.warning("첨부 추가 일부 실패 (page=%s): %s", page_id, failed)
    final = await notion.get_page(page_id)
    item = _from_notion_page(final)
    # PR-BX: 첨부 추가 partial failure를 정형 응답에 포함.
    # PR-CA: 노션 update 실패도 분류 (helper 재사용).
    item.partial_errors = [_failed_to_partial(msg) for msg in failed]
    return item


@router.post("/{page_id}/redo", response_model=SealRequestItem)
async def redo_seal_request(
    page_id: str,
    body: SealRedoBody,
    user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
    db: Session = Depends(get_db),
) -> SealRequestItem:
    """재날인요청 — 같은 노션 row를 update해 새 1차검토 사이클 시작.

    docs/request.md 정책:
    - DB row는 새로 만들지 않고 기존 row 덮어쓰기.
    - 모든 입력 필드를 update + 상태='1차검토 중' + 처리자/반려사유 reset.
    - 구조검토서의 문서번호는 이전 값 유지(새로 발급 X).
    - 자동 TASK 흐름은 정상 — 요청자 + 1차 검토자 TASK를 새로 생성.
      (이전 사이클의 TASK들은 완료 상태 그대로 보존하여 history.)
    """
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
        cur_title = ""
        for v in props.values():
            if isinstance(v, dict) and v.get("type") == "title":
                arr = v.get("title") or []
                cur_title = arr[0].get("plain_text", "") if arr else ""
                break
        new_title = (
            cur_title if cur_title.startswith("[날인취소] ") else f"[날인취소] {cur_title}"
        )
        title_prop = await _get_title_prop_name(notion)
        await notion.update_page(
            page_id,
            {
                title_prop: {"title": [{"text": {"content": new_title}}]},
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

    # 연결 task 완료 처리 (요청자 + 검토자 모두) — 취소도 라이프사이클 종료로 간주.
    # 진행 단계='완료' + 기간.end=오늘. 노션에 흔적이 남아 사후 조회 가능.
    for tid in (item.linked_task_id, item.lead_task_id, item.admin_task_id):
        if tid:
            await _sync_linked_task(notion, tid, target="완료")

    notion.clear_cache()
    return {
        "status": "marked-cancelled" if keep_with_marker else "archived",
    }


# ── PR-CG/CH sub-router include (파일 끝 — 모든 helper 정의 후) ──
from app.routers.seal_requests import attachments as _attachments  # noqa: E402
from app.routers.seal_requests import meta as _meta  # noqa: E402

router.include_router(_meta.router)
router.include_router(_attachments.router)
