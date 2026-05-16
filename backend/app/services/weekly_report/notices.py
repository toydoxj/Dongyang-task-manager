"""공휴일·공지/교육 aggregate.

PR-DJ (Phase 4-J 20단계): weekly_report/__init__.py에서 분리.

| 함수 | 출력 | source |
|---|---|---|
| `aggregate_holidays` | `list[HolidayItem]` | `holidays` lib (법정·대체) + `Notice` kind='휴일' (사내) |
| `aggregate_notices` | `(notices, education)` | `Notice` kind='공지'/'교육' |

두 함수 모두 단순 DB query — N+1 / bulk pre-fetch 로직 없음. helper 의존
없음(pure SQLAlchemy + holidays lib).

`HolidayItem` model은 __init__.py에 그대로 두고 import. build_weekly_report
직전에 본 모듈을 import하므로 partial loading 시점에 attribute 확보됨
(PR-DI/DH/DE 검증 패턴).
"""
from __future__ import annotations

from datetime import date, timedelta

import holidays
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.notice import Notice
from app.services.weekly_report import HolidayItem


def aggregate_holidays(
    db: Session, week_start: date, week_end: date
) -> list[HolidayItem]:
    """주차 내 공휴일/사내휴일 — 법정(holidays lib) + notices kind='휴일' 합치기.

    동일 날짜에 두 source가 겹치면 사내(company) 먼저 + 법정 뒤 (frontend에서
    구분 표시 가능). 정렬: 날짜 오름차순.
    """
    items: list[HolidayItem] = []
    # 법정공휴일 — 대체공휴일 포함
    kr = holidays.country_holidays("KR", years=[week_start.year, week_end.year])
    cur = week_start
    while cur <= week_end:
        name = kr.get(cur)
        if name:
            items.append(HolidayItem(date=cur, name=name, source="legal"))
        cur = cur + timedelta(days=1)
    # 사내휴일 — notices kind='휴일' 게시기간 교집합
    company_rows = (
        db.query(Notice)
        .filter(Notice.kind == "휴일")
        .filter(Notice.start_date <= week_end)
        .filter(or_(Notice.end_date.is_(None), Notice.end_date >= week_start))
        .all()
    )
    for n in company_rows:
        # 게시기간이 주차와 교집합인 모든 일자에 등록
        s = max(n.start_date, week_start)
        e = min(n.end_date or week_end, week_end)
        cur = s
        while cur <= e:
            items.append(HolidayItem(date=cur, name=n.title, source="company"))
            cur = cur + timedelta(days=1)
    items.sort(key=lambda h: (h.date, 0 if h.source == "company" else 1))
    return items


def aggregate_notices(
    db: Session, week_start: date, week_end: date
) -> tuple[list[str], list[str]]:
    """게시기간이 주차와 겹치는 공지/교육의 title list 반환 — (notices, education).

    end_date NULL = 무기한 게시. start_date <= week_end and (end_date IS NULL or end_date >= week_start).
    """
    rows = (
        db.query(Notice)
        .filter(Notice.start_date <= week_end)
        .filter(or_(Notice.end_date.is_(None), Notice.end_date >= week_start))
        .order_by(Notice.start_date.desc(), Notice.id.desc())
        .all()
    )
    notices: list[str] = []
    education: list[str] = []
    for r in rows:
        if r.kind == "교육":
            education.append(r.title)
        else:
            notices.append(r.title)
    return notices, education
