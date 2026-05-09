"""주간 업무일지 PDF 빌더 — frontend `/weekly-report` 페이지와 동일 양식.

Jinja2 + WeasyPrint. paged media 특성상 일부 layout(특히 grid/flex)은
프린트 호환을 위해 단순화. 기본 골격은 frontend ReportPreview와 동일.
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


def _krw(value: int | float | None) -> str:
    if value is None or value == 0:
        return ""
    return f"₩{int(value):,}"


def _mmdd(iso: str | None) -> str:
    """YYYY-MM-DD → MM/DD."""
    if not iso:
        return ""
    return iso[5:10].replace("-", "/")


def _read_logo_svg() -> str:
    if not _LOGO_PATH.exists():
        return ""
    text = _LOGO_PATH.read_text(encoding="utf-8")
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end != -1:
            text = text[end + 2 :].lstrip()
    return text


_env.filters["krw"] = _krw
_env.filters["mmdd"] = _mmdd


def _build_schedule_by_employee(
    report: WeeklyReport,
) -> dict[str, list[list[dict]]]:
    """{employee: [day0..dayN entries]} — frontend buildScheduleByEmployee와 동일.

    각 cell은 list of {category, kind, project_code} (한 직원의 한 날에 N개 가능).
    """
    week_start = report.period_start
    week_end = report.period_end
    day_count = (week_end - week_start).days + 1
    if day_count < 1:
        day_count = 1

    matrix: dict[str, list[list[dict]]] = {}
    for entry in report.personal_schedule:
        try:
            sd = date.fromisoformat(entry.start_date)
            ed = date.fromisoformat(entry.end_date)
        except ValueError:
            continue
        if entry.employee_name not in matrix:
            matrix[entry.employee_name] = [[] for _ in range(day_count)]
        for offset in range(day_count):
            day = week_start + timedelta(days=offset)
            if sd <= day <= ed:
                matrix[entry.employee_name][offset].append(
                    {
                        "category": entry.category,
                        "kind": entry.kind,
                        "project_code": entry.project_code,
                    }
                )
    return matrix


def _build_week_days(report: WeeklyReport) -> list[dict]:
    """[{iso, label, is_holiday, holiday_names}] — frontend buildWeekDays + 공휴일."""
    KOR = ["일", "월", "화", "수", "목", "금", "토"]
    holiday_by_iso: dict[str, list[str]] = defaultdict(list)
    for h in report.holidays:
        holiday_by_iso[h.date.isoformat()].append(h.name)

    days: list[dict] = []
    cur = report.period_start
    while cur <= report.period_end:
        iso = cur.isoformat()
        names = holiday_by_iso.get(iso, [])
        days.append(
            {
                "iso": iso,
                "label": KOR[cur.weekday() if cur.weekday() < 6 else 6],  # weekday: Mon=0
                # Python weekday: Mon=0..Sun=6, Korean array는 일=0 시작 → 매핑 다름
                # 직접: 월=1,화=2..일=0
                "is_holiday": bool(names),
                "holiday_names": names,
            }
        )
        cur = cur + timedelta(days=1)
    # weekday 라벨 정확히 (Python Date.weekday(): Mon=0..Sun=6)
    KOR_FROM_WD = ["월", "화", "수", "목", "금", "토", "일"]
    cur = report.period_start
    for d in days:
        d["label"] = KOR_FROM_WD[cur.weekday()]
        cur = cur + timedelta(days=1)
    return days


def _format_period(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.day}일"
    if start.year == end.year:
        return f"{start.year}년 {start.month}월 {start.day}일 ~ {end.month}월 {end.day}일"
    return f"{start.strftime('%Y년 %m월 %d일')} ~ {end.strftime('%Y년 %m월 %d일')}"


_TEAM_ORDER = {"구조1팀": 1, "구조2팀": 2, "구조3팀": 3, "구조4팀": 4, "진단팀": 5, "본부": 6}


def _team_sort_key(name: str) -> tuple[int, str]:
    return (_TEAM_ORDER.get(name, 99), name)


SCHEDULE_GRID_TEAMS = ("구조1팀", "구조2팀", "구조3팀", "구조4팀", "진단팀")
SCHEDULE_EXTRA_TEAM = "본부"


def build_weekly_report_pdf(report: WeeklyReport) -> bytes:
    """WeeklyReport DTO → PDF bytes (frontend 양식 동등)."""
    template = _env.get_template("weekly_report.html")
    schedule_by_employee = _build_schedule_by_employee(report)
    week_days = _build_week_days(report)
    team_work_sorted = sorted(report.team_work.items(), key=lambda kv: _team_sort_key(kv[0]))
    # team_work 그룹화: 같은 직원 첫 row만 이름/직책 표시 위해 rowspan 계산
    team_work_grouped: dict[str, list[dict]] = {}
    for team, rows in team_work_sorted:
        rendered = []
        for i, r in enumerate(rows):
            prev = rows[i - 1] if i > 0 else None
            is_first = (prev is None) or (prev.employee_name != r.employee_name)
            rowspan = 1
            if is_first:
                for j in range(i + 1, len(rows)):
                    if rows[j].employee_name == r.employee_name:
                        rowspan += 1
                    else:
                        break
            rendered.append({"row": r, "is_first": is_first, "rowspan": rowspan})
        team_work_grouped[team] = rendered

    html = template.render(
        report=report,
        period_label=_format_period(report.period_start, report.period_end),
        week_days=week_days,
        schedule_by_employee=schedule_by_employee,
        team_work_grouped=team_work_grouped,
        team_work_team_order=[t for t, _ in team_work_sorted],
        schedule_grid_teams=SCHEDULE_GRID_TEAMS,
        schedule_extra_team=SCHEDULE_EXTRA_TEAM,
        logo_svg=_read_logo_svg(),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    return HTML(string=html).write_pdf()
