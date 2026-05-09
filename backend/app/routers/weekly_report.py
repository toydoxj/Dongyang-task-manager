"""주간 업무일지 라우터 (PR-W Phase 1).

GET /api/weekly-report — JSON
GET /api/weekly-report.pdf — WeasyPrint PDF

권한: 로그인 사용자 누구나 (member 이상). 자기 팀만 보는 필터는 1차에서는 미적용
— 모든 직원이 회사 전체 일지를 보는 현행 정책 유지.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.security import get_current_user
from app.services.weekly_report import WeeklyReport, build_weekly_report
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


@router.get("", response_model=WeeklyReport)
def get_weekly_report(
    week_start: date = Query(..., description="주차 시작일 — 월요일 (YYYY-MM-DD)"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeeklyReport:
    """주간 업무일지 JSON.

    week_start가 월요일이 아니면 같은 주의 월요일로 자동 조정.
    """
    ws = _validate_week_start(week_start)
    try:
        return build_weekly_report(db, ws)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(".pdf")
def get_weekly_report_pdf(
    week_start: date = Query(..., description="주차 시작일 — 월요일 (YYYY-MM-DD)"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """주간 업무일지 PDF (WeasyPrint)."""
    ws = _validate_week_start(week_start)
    try:
        report = build_weekly_report(db, ws)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
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
