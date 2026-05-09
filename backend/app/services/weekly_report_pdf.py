"""주간 업무일지 PDF 빌더 (PR-W Phase 1).

Jinja2 + WeasyPrint. PLAN_WEEKLY_REPORT.md의 4페이지 양식을 1차 재현.
실물 PDF 샘플은 repo에 부재 — PLAN의 텍스트 설명 기반.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.services.weekly_report import WeeklyReport

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_LOGO_PATH = _TEMPLATE_DIR / "dongyang_logo.svg"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _pct(value: float | None) -> str:
    """0~1 범위 progress를 '83%' 형식으로. None/0은 '0%'."""
    if value is None:
        return "0%"
    return f"{int(round(value * 100))}%"


def _krw(value: int | float | None) -> str:
    if value is None or value == 0:
        return ""
    return f"₩{int(value):,}"


def _read_logo_svg() -> str:
    if not _LOGO_PATH.exists():
        return ""
    text = _LOGO_PATH.read_text(encoding="utf-8")
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end != -1:
            text = text[end + 2 :].lstrip()
    return text


_env.filters["pct"] = _pct
_env.filters["krw"] = _krw


def _build_schedule_matrix(report: WeeklyReport) -> dict[str, dict[str, list[dict]]]:
    """직원×요일 매트릭스 — {team: {employee: [day0..day4 entries]}} 형태.

    각 cell은 list of {category, note, project_code} (한 직원이 한 날에 여러 일정 가능).
    """
    week_start = report.period_start
    matrix: dict[str, dict[str, list[list[dict]]]] = defaultdict(lambda: defaultdict(lambda: [[] for _ in range(5)]))

    for entry in report.personal_schedule:
        try:
            sd = date.fromisoformat(entry.start_date)
            ed = date.fromisoformat(entry.end_date)
        except ValueError:
            continue
        for offset in range(5):
            day = week_start + timedelta(days=offset)
            if sd <= day <= ed:
                cell = matrix[entry.team or "기타"][entry.employee_name][offset]
                cell.append(
                    {
                        "category": entry.category,
                        "note": entry.note,
                        "project_code": entry.project_code,
                    }
                )
    return {team: dict(emps) for team, emps in matrix.items()}


def _format_period(start: date, end: date) -> str:
    """'2026년 4월 27일 ~ 5월 1일' 형식."""
    if start.year == end.year and start.month == end.month:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.day}일"
    if start.year == end.year:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"
    return f"{start.strftime('%Y년 %m월 %d일')} ~ {end.strftime('%Y년 %m월 %d일')}"


def _team_sort_key(team_name: str) -> tuple[int, str]:
    """팀 정렬 — 구조1팀 < 구조2팀 < ... < 진단팀 < 기타."""
    order_map = {"구조1팀": 1, "구조2팀": 2, "구조3팀": 3, "구조4팀": 4, "진단팀": 5}
    return (order_map.get(team_name, 99), team_name)


def build_weekly_report_pdf(report: WeeklyReport) -> bytes:
    """WeeklyReport DTO → PDF bytes."""
    template = _env.get_template("weekly_report.html")
    schedule_matrix = _build_schedule_matrix(report)
    sorted_teams = sorted(report.teams.items(), key=lambda kv: _team_sort_key(kv[0]))

    html = template.render(
        report=report,
        period_label=_format_period(report.period_start, report.period_end),
        weekday_labels=["월", "화", "수", "목", "금"],
        schedule_matrix=schedule_matrix,
        sorted_teams=sorted_teams,
        logo_svg=_read_logo_svg(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return HTML(string=html).write_pdf()
