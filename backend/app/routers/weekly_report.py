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
from app.security import get_current_user
from app.services.notion import NotionService, get_notion
from app.services.weekly_report import (
    SealLogItem,
    WeeklyReport,
    build_weekly_report,
)
from app.services.weekly_report_pdf import build_weekly_report_pdf

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


async def _build_seal_log(
    user: User,
    notion: NotionService,
    db: Session,
    week_start: date,
    week_end: date,
) -> list[SealLogItem]:
    """주차 내 활성 날인요청 list. admin/team_lead만 회사 전체 조회.

    list_seal_requests 함수를 그대로 호출 (권한·정렬 로직 재사용). 결과 중
    제출예정일 또는 요청일이 [week_start, week_end]와 겹치는 항목 + 진행 중인
    승인/반려 외 status를 SealLogItem으로 변환.
    """
    if user.role not in {"admin", "team_lead"}:
        return []
    # 동적 import — 순환 의존성 회피
    from app.routers.seal_requests import list_seal_requests

    try:
        res = await list_seal_requests(
            project_id=None, user=user, notion=notion, db=db
        )
    except HTTPException as e:
        logger.warning("날인대장 조회 실패: %s", e.detail)
        return []

    week_start_iso = week_start.isoformat()
    week_end_iso = week_end.isoformat()

    # mirror_projects.code/name lookup — relation page_id → 표시 라벨
    proj_label_by_id: dict[str, tuple[str, str]] = {}
    client_name_by_id: dict[str, str] = {
        c.page_id: c.name or ""
        for c in db.query(M.MirrorClient.page_id, M.MirrorClient.name).all()
    }
    proj_meta = (
        db.query(
            M.MirrorProject.page_id,
            M.MirrorProject.code,
            M.MirrorProject.name,
            M.MirrorProject.properties,
        ).all()
    )
    for pid, code, name, props in proj_meta:
        # 발주처 — relation 첫 번째 → mirror_clients 이름
        client_name = ""
        rel = (props or {}).get("발주처", {}).get("relation") or []
        if rel:
            client_name = client_name_by_id.get(rel[0].get("id", ""), "")
        proj_label_by_id[pid] = (f"[{code}] {name}" if code else name, client_name)

    items: list[SealLogItem] = []
    for s in res.items:
        # 주차 교집합: 제출예정일 또는 요청일 중 하나라도 주차 범위 내
        date_in_week = False
        for d_iso in (s.due_date, s.requested_at):
            if d_iso and week_start_iso <= d_iso[:10] <= week_end_iso:
                date_in_week = True
                break
        if not date_in_week:
            continue
        proj_label, client = "", ""
        if s.project_ids:
            proj_label, client = proj_label_by_id.get(s.project_ids[0], ("", ""))
        # 현재 단계별 처리자
        if s.status == "1차검토 중":
            handler = s.lead_handler or s.requester
        elif s.status == "2차검토 중":
            handler = s.admin_handler or s.lead_handler or s.requester
        else:
            handler = s.admin_handler or s.lead_handler or s.requester
        items.append(
            SealLogItem(
                project_name=proj_label,
                client=client,
                seal_type=s.seal_type,
                status=s.status,
                handler=handler,
                due_date=s.due_date,
                requested_at=s.requested_at,
            )
        )
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
    report.seal_log = await _build_seal_log(
        user, notion, db, report.period_start, report.period_end
    )
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
    report.seal_log = await _build_seal_log(
        user, notion, db, report.period_start, report.period_end
    )
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
