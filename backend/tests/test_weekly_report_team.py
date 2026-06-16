"""주간 업무일지 팀별 업무 집계 회귀 테스트."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import cast

from app.models import mirror as M
from app.services.weekly_report.helpers import _is_employee_active_for_week
from app.services.weekly_report.team import _task_overlaps_period


def _task(
    *,
    start_date: date | None,
    end_date: date | None,
    actual_end_date: date | None,
) -> M.MirrorTask:
    """테스트용 최소 task 객체."""
    return cast(
        M.MirrorTask,
        SimpleNamespace(
            start_date=start_date,
            end_date=end_date,
            actual_end_date=actual_end_date,
        ),
    )


def test_completed_open_ended_task_does_not_overlap_future_week() -> None:
    """완료일만 있고 예상 완료일이 빈 task는 이후 주차 금주업무에 남지 않는다."""
    task = _task(
        start_date=date(2026, 5, 10),
        end_date=None,
        actual_end_date=date(2026, 5, 10),
    )

    assert _task_overlaps_period(task, date(2026, 6, 1), date(2026, 6, 5)) is False


def test_completed_open_ended_task_overlaps_actual_completion_week() -> None:
    """실제 완료일이 포함된 주차에는 지난주 업무로 집계될 수 있다."""
    task = _task(
        start_date=date(2026, 5, 10),
        end_date=None,
        actual_end_date=date(2026, 5, 10),
    )

    assert _task_overlaps_period(task, date(2026, 5, 4), date(2026, 5, 10)) is True


def test_open_task_without_actual_end_stays_active() -> None:
    """미완료 open-ended task는 기존처럼 이후 주차에도 활성으로 본다."""
    task = _task(
        start_date=date(2026, 5, 10),
        end_date=None,
        actual_end_date=None,
    )

    assert _task_overlaps_period(task, date(2026, 6, 1), date(2026, 6, 5)) is True


def test_employee_active_for_week_excludes_resigned_before_week_end() -> None:
    assert _is_employee_active_for_week(date(2026, 6, 3), date(2026, 6, 5)) is False


def test_employee_active_for_week_includes_future_resignation() -> None:
    assert _is_employee_active_for_week(date(2026, 6, 8), date(2026, 6, 5)) is True
