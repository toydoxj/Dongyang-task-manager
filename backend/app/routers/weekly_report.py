"""주간 업무일지 라우터 (PR-W Phase 1).

GET /api/weekly-report — JSON
GET /api/weekly-report.pdf — WeasyPrint PDF

권한: 로그인 사용자 누구나 (member 이상). 자기 팀만 보는 필터는 1차에서는 미적용
— 모든 직원이 회사 전체 일지를 보는 현행 정책 유지.

날인대장은 admin/team_lead만 조회 가능 (기존 list_seal_requests 권한 정책 따름).
일반 직원이 보면 seal_log는 빈 list.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.employee import Employee
from app.models.weekly_publish import WeeklyReportPublishLog
from app.security import get_current_user, require_admin
from app.services import sso_drive, sso_works_bot
from app.services.notion import NotionService, get_notion
from app.services.weekly_report import (
    SealLogItem,
    SuggestionLogItem,
    WeeklyReport,
    build_weekly_report,
)
from app.services.weekly_report_pdf import build_weekly_report_pdf
from pydantic import BaseModel

logger = logging.getLogger("weekly_report")

router = APIRouter(prefix="/weekly-report", tags=["weekly_report"])


def _validate_week_start(week_start: date) -> date:
    """월요일이 아니면 그 주의 월요일로 정규화 + 경고."""
    if week_start.weekday() != 0:
        adjusted = week_start - timedelta(days=week_start.weekday())
        logger.info(
            "weekly_report week_start %s가 월요일이 아님 → %s로 조정",
            week_start.isoformat(),
            adjusted.isoformat(),
        )
        return adjusted
    return week_start


async def _build_suggestions(
    user: User,
    notion: NotionService,
    last_week_start: date,
    last_week_end: date,
) -> list[SuggestionLogItem]:
    """저번주 cycle 등록된 건의사항 (created_time 기준)."""
    from app.routers.suggestions import list_suggestions

    try:
        res = await list_suggestions(_user=user, notion=notion)
    except HTTPException as e:
        logger.warning("suggestions 조회 실패: %s", e.detail)
        return []
    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()
    items: list[SuggestionLogItem] = []
    for s in res.items:
        ct = (s.created_time or "")[:10]
        if not ct or not (range_start_iso <= ct <= range_end_iso):
            continue
        items.append(
            SuggestionLogItem(
                title=s.title,
                author=s.author,
                status=s.status,
                created_at=s.created_time,
            )
        )
    return items


async def _build_seal_log(
    user: User,
    notion: NotionService,
    db: Session,
    last_week_start: date,
    last_week_end: date,
) -> list[SealLogItem]:
    """저번주 범위에 최종 승인된 날인요청만 (PR-W 사용자 결정 2026-05-09).

    필터:
    - status='승인'
    - admin_handled_at(최종 승인일)이 [last_week_start, last_week_end] 안

    표시:
    - project_name: "{코드} {용역명}"
    - submission_target: real_source_id가 있으면 거래처명, 없으면 발주처
    - requester: 담당자(요청자)

    admin/team_lead만 회사 전체 조회 (list_seal_requests의 기존 권한 따름).
    """
    if user.role not in {"admin", "team_lead"}:
        return []
    from app.routers.seal_requests import list_seal_requests

    try:
        res = await list_seal_requests(
            project_id=None, user=user, notion=notion, db=db
        )
    except HTTPException as e:
        logger.warning("날인대장 조회 실패: %s", e.detail)
        return []

    range_start_iso = last_week_start.isoformat()
    range_end_iso = last_week_end.isoformat()

    # mirror_clients lookup — page_id → name
    client_name_by_id: dict[str, str] = {
        c.page_id: c.name or ""
        for c in db.query(M.MirrorClient.page_id, M.MirrorClient.name).all()
    }
    # mirror_projects → (code, name, 발주처명)
    proj_meta_by_id: dict[str, tuple[str, str, str]] = {}
    proj_meta = db.query(
        M.MirrorProject.page_id,
        M.MirrorProject.code,
        M.MirrorProject.name,
        M.MirrorProject.properties,
    ).all()
    for pid, code, name, props in proj_meta:
        client_name = ""
        rel = (props or {}).get("발주처", {}).get("relation") or []
        if rel:
            client_name = client_name_by_id.get(rel[0].get("id", ""), "")
        proj_meta_by_id[pid] = (code or "", name or "", client_name)

    items: list[SealLogItem] = []
    for s in res.items:
        if s.status != "승인":
            continue
        approved = s.admin_handled_at
        if not approved or not (range_start_iso <= approved[:10] <= range_end_iso):
            continue
        code, name, project_client = "", "", ""
        if s.project_ids:
            code, name, project_client = proj_meta_by_id.get(
                s.project_ids[0], ("", "", "")
            )
        # 제출처: real_source_id 우선 → mirror_clients lookup, fallback 발주처
        submission_target = ""
        if s.real_source_id:
            submission_target = client_name_by_id.get(s.real_source_id, "")
        if not submission_target:
            submission_target = project_client
        # 유형: 구조계산서 + 구조안전확인서 포함 → "계산서(w/안전)"
        seal_type = s.seal_type
        if seal_type == "구조계산서" and s.with_safety_cert:
            seal_type = "계산서(w/안전)"
        items.append(
            SealLogItem(
                project_id=s.project_ids[0] if s.project_ids else "",
                code=code,
                name=name,
                submission_target=submission_target,
                seal_type=seal_type,
                requester=s.requester,
                approved_at=approved,
            )
        )
    items.sort(key=lambda it: it.approved_at or "")
    return items


@router.get("", response_model=WeeklyReport)
async def get_weekly_report(
    week_start: date = Query(..., description="이번주 시작일 — 월요일 (YYYY-MM-DD)"),
    week_end: date | None = Query(
        None, description="이번주 종료일 (YYYY-MM-DD). default: week_start + 4일"
    ),
    last_week_start: date | None = Query(
        None,
        description="지난주 시작일 (YYYY-MM-DD). default: week_start - 7일",
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> WeeklyReport:
    """주간 업무일지 JSON.

    week_start가 월요일이 아니면 같은 주의 월요일로 자동 조정.
    날인대장은 admin/team_lead만 채워짐 (일반직원은 빈 list).
    """
    ws = _validate_week_start(week_start)
    try:
        report = build_weekly_report(
            db, ws, week_end=week_end, last_week_start=last_week_start
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 저번주 범위 (build_weekly_report와 동일 로직):
    lws = last_week_start or (ws - timedelta(days=7))
    lwe = ws - timedelta(days=1)
    report.seal_log = await _build_seal_log(user, notion, db, lws, lwe)
    report.suggestions = await _build_suggestions(user, notion, lws, lwe)
    return report


@router.get(".pdf")
async def get_weekly_report_pdf(
    week_start: date = Query(..., description="이번주 시작일 — 월요일 (YYYY-MM-DD)"),
    week_end: date | None = Query(None),
    last_week_start: date | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Response:
    """주간 업무일지 PDF (WeasyPrint)."""
    ws = _validate_week_start(week_start)
    try:
        report = build_weekly_report(
            db, ws, week_end=week_end, last_week_start=last_week_start
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 저번주 범위 (build_weekly_report와 동일 로직):
    lws = last_week_start or (ws - timedelta(days=7))
    lwe = ws - timedelta(days=1)
    report.seal_log = await _build_seal_log(user, notion, db, lws, lwe)
    report.suggestions = await _build_suggestions(user, notion, lws, lwe)
    pdf_bytes = build_weekly_report_pdf(report)
    fname = f"{ws.strftime('%Y_%m_%d')}_업무일지.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{url_quote(fname)}"
            ),
        },
    )


# ── 발행 (PUBLISH) — admin only ─────────────────────────────────────────


class PublishRequest(BaseModel):
    week_start: date
    week_end: date | None = None
    last_week_start: date | None = None


class PublishResponse(BaseModel):
    file_id: str
    file_url: str
    file_name: str
    recipient_count: int
    notify_failed_count: int
    log_id: int


class LastPublishedResponse(BaseModel):
    week_start: date | None = None
    week_end: date | None = None
    published_at: str | None = None


_PUBLISH_FOLDER_NAME = "주간업무일지"


async def _resolve_publish_folder() -> str:
    """[주간업무일지] 폴더 file_id 반환 — 없으면 sharedrive root에 새로 생성.

    create_folder는 409 발생 시 기존 폴더 재조회로 idempotent 처리.
    """
    settings = sso_drive.get_settings()
    if not settings.works_drive_root_folder_id:
        raise sso_drive.DriveError("WORKS_DRIVE_ROOT_FOLDER_ID 미설정")
    meta = await sso_drive.create_folder(
        settings, settings.works_drive_root_folder_id, _PUBLISH_FOLDER_NAME
    )
    return meta.get("file", {}).get("fileId") or meta.get("fileId") or ""


def _format_period_short(start: date, end: date) -> str:
    """알림용 기간 — 'MMDD~MMDD' (월일만)."""
    return f"{start.strftime('%m%d')}~{end.strftime('%m%d')}"


@router.post("/publish", response_model=PublishResponse)
async def publish_weekly_report(
    body: PublishRequest,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> PublishResponse:
    """주간 업무일지 발행 — admin only.

    1. PDF 빌드
    2. WORKS Drive `[주간업무일지]/{YYYYMMDD}_주간업무일지.pdf` 업로드
    3. 전직원(works_user_id 또는 email 있는 active employees) 에게 bot 알림
    4. publish log 저장 (다음 일지의 last_week_start 자동 셋팅 기준)
    """
    ws = _validate_week_start(body.week_start)
    try:
        report = build_weekly_report(
            db, ws, week_end=body.week_end, last_week_start=body.last_week_start
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    lws = body.last_week_start or (ws - timedelta(days=7))
    lwe = ws - timedelta(days=1)
    report.seal_log = await _build_seal_log(user, notion, db, lws, lwe)
    report.suggestions = await _build_suggestions(user, notion, lws, lwe)

    pdf_bytes = build_weekly_report_pdf(report)
    file_name = f"{ws.strftime('%Y%m%d')}_주간업무일지.pdf"

    # WORKS Drive 업로드 — 실패 시 즉시 500 (publish 실패).
    try:
        folder_id = await _resolve_publish_folder()
        upload_result = await sso_drive.upload_file(
            folder_id,
            file_name,
            pdf_bytes,
            content_type="application/pdf",
        )
    except sso_drive.DriveError as e:
        raise HTTPException(
            status_code=500, detail=f"WORKS Drive 업로드 실패: {e}"
        )
    file_id = upload_result.get("fileId") or upload_result.get("file", {}).get("fileId") or ""
    file_url = upload_result.get("fileUrl") or upload_result.get("webUrl") or ""

    # 전직원 알림 — works_user_id 우선, 없으면 email. 둘 다 없으면 skip.
    recipients = db.query(Employee).all()
    period_short = _format_period_short(report.period_start, report.period_end)
    notify_text = f"{period_short} 주간업무일지가 업로드 되었습니다."
    sent_count = 0
    failed_count = 0
    for emp in recipients:
        target = (emp.works_user_id or "").strip() or (emp.email or "").strip()
        if not target:
            continue
        try:
            ok = await sso_works_bot.send_text(target, notify_text)
        except Exception as e:  # noqa: BLE001
            logger.warning("publish notify exception (%s): %s", target, e)
            ok = False
        if ok:
            sent_count += 1
        else:
            failed_count += 1

    log = WeeklyReportPublishLog(
        week_start=ws,
        week_end=report.period_end,
        last_week_start=lws,
        last_week_end=lwe,
        published_by=user.name or user.email or "",
        file_id=file_id,
        file_url=file_url,
        file_name=file_name,
        recipient_count=sent_count,
        notify_failed_count=failed_count,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return PublishResponse(
        file_id=file_id,
        file_url=file_url,
        file_name=file_name,
        recipient_count=sent_count,
        notify_failed_count=failed_count,
        log_id=log.id,
    )


@router.get("/last-published", response_model=LastPublishedResponse)
def get_last_published(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LastPublishedResponse:
    """가장 최근 발행된 일지의 week_start/week_end. 다음 일지 작성 시
    last_week_start 자동 셋팅의 근거. 발행 이력이 없으면 None.
    """
    log = (
        db.query(WeeklyReportPublishLog)
        .order_by(WeeklyReportPublishLog.published_at.desc())
        .first()
    )
    if not log:
        return LastPublishedResponse()
    return LastPublishedResponse(
        week_start=log.week_start,
        week_end=log.week_end,
        published_at=log.published_at.isoformat() if log.published_at else None,
    )


@router.get("/last-published.pdf")
async def download_last_published_pdf(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Response:
    """가장 최근 발행된 일지의 PDF — 비admin이 다운로드.

    publish 시점의 week_start/week_end로 다시 빌드한다 (WORKS Drive에 저장된
    PDF를 backend가 다시 fetch하지 않음). 데이터는 publish 이후 변할 수 있지만
    구간이 같으므로 발행본과 사실상 동일.
    """
    log = (
        db.query(WeeklyReportPublishLog)
        .order_by(WeeklyReportPublishLog.published_at.desc())
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="발행된 주간업무일지가 없습니다")
    try:
        report = build_weekly_report(
            db,
            log.week_start,
            week_end=log.week_end,
            last_week_start=log.last_week_start,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    lws = log.last_week_start or (log.week_start - timedelta(days=7))
    lwe = log.last_week_end or (log.week_start - timedelta(days=1))
    report.seal_log = await _build_seal_log(user, notion, db, lws, lwe)
    report.suggestions = await _build_suggestions(user, notion, lws, lwe)
    pdf_bytes = build_weekly_report_pdf(report)
    fname = log.file_name or f"{log.week_start.strftime('%Y%m%d')}_주간업무일지.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename*=UTF-8''{url_quote(fname)}"
            ),
        },
    )
