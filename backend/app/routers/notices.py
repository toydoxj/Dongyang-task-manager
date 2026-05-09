"""사내 공지 / 교육 일정 라우터 (PR-W Phase 2.4).

GET /api/notices                   member 이상, 필터(week_start, kind)
POST /api/notices                  admin
PATCH /api/notices/{id}            admin
DELETE /api/notices/{id}           admin

게시기간 필터(`week_start`)가 있으면 해당 주차(월~금)와 겹치는 row만 반환.
없으면 최근 등록 순 전체 (admin 관리 페이지용).
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.notice import (
    Notice,
    NoticeCreate,
    NoticeListResponse,
    NoticeOut,
    NoticeUpdate,
)
from app.security import get_current_user, require_admin

router = APIRouter(prefix="/notices", tags=["notices"])

_VALID_KINDS = {"공지", "교육", "휴일"}


def _validate_kind(kind: str) -> None:
    if kind not in _VALID_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind는 {sorted(_VALID_KINDS)} 중 하나여야 합니다 (입력: {kind!r})",
        )


@router.get("", response_model=NoticeListResponse)
def list_notices(
    week_start: date | None = Query(
        None, description="주차 시작일 (월요일). 지정 시 해당 주차와 겹치는 row만"
    ),
    kind: str | None = Query(None, description="공지 | 교육 — 미지정 시 전체"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    q = db.query(Notice)
    if kind:
        _validate_kind(kind)
        q = q.filter(Notice.kind == kind)
    if week_start is not None:
        week_end = week_start + timedelta(days=4)
        # 게시기간이 [week_start, week_end]와 교집합. end_date NULL = 무기한.
        q = q.filter(Notice.start_date <= week_end).filter(
            or_(Notice.end_date.is_(None), Notice.end_date >= week_start)
        )
    rows = q.order_by(Notice.start_date.desc(), Notice.id.desc()).all()
    return NoticeListResponse(
        items=[NoticeOut.model_validate(r) for r in rows], count=len(rows)
    )


@router.post("", response_model=NoticeOut, status_code=status.HTTP_201_CREATED)
def create_notice(
    body: NoticeCreate,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NoticeOut:
    _validate_kind(body.kind)
    if body.end_date is not None and body.end_date < body.start_date:
        raise HTTPException(
            status_code=400, detail="end_date는 start_date 이상이어야 합니다"
        )
    row = Notice(
        kind=body.kind,
        title=body.title,
        body=body.body,
        start_date=body.start_date,
        end_date=body.end_date,
        author_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return NoticeOut.model_validate(row)


@router.patch("/{notice_id}", response_model=NoticeOut)
def update_notice(
    notice_id: int,
    body: NoticeUpdate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NoticeOut:
    row = db.get(Notice, notice_id)
    if row is None:
        raise HTTPException(status_code=404, detail="공지를 찾을 수 없습니다")
    if body.kind is not None:
        _validate_kind(body.kind)
        row.kind = body.kind
    if body.title is not None:
        row.title = body.title
    if body.body is not None:
        row.body = body.body
    if body.start_date is not None:
        row.start_date = body.start_date
    if body.end_date is not None:
        row.end_date = body.end_date
    if (
        row.end_date is not None
        and row.start_date is not None
        and row.end_date < row.start_date
    ):
        raise HTTPException(
            status_code=400, detail="end_date는 start_date 이상이어야 합니다"
        )
    db.commit()
    db.refresh(row)
    return NoticeOut.model_validate(row)


@router.delete("/{notice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notice(
    notice_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(Notice, notice_id)
    if row is None:
        raise HTTPException(status_code=404, detail="공지를 찾을 수 없습니다")
    db.delete(row)
    db.commit()
