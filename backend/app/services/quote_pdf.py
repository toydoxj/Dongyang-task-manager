"""견적서 PDF 출력 — Jinja2 HTML 템플릿 + WeasyPrint.

xlsx 양식과 별개의 새 디자인. A4 1페이지에 회사 정보·서명란까지 포함.
시스템 의존성(cairo/pango/fonts-nanum)은 Dockerfile에서 install.

xlsx의 양식 보존 책임에서 분리되어 디자인 자유도가 높음 — 향후 양식 변경
시 templates/quote_template.html만 수정.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _krw(value: int | float | None) -> str:
    """₩ 표기 — None/0/빈 값은 빈 문자열로."""
    if value is None or value == 0:
        return ""
    return f"{int(value):,}원"


_env.filters["krw"] = _krw


def build_quote_pdf(
    form_data: dict[str, Any], *, doc_number: str = ""
) -> bytes:
    """form_data['input'] + ['result']를 quote_template.html로 렌더링 → PDF bytes."""
    template = _env.get_template("quote_template.html")
    inp = form_data.get("input") or {}
    result = form_data.get("result") or {}

    html = template.render(
        doc_number=doc_number,
        input=inp,
        result=result,
        today=date.today().strftime("%Y. %m. %d"),
    )
    return HTML(string=html).write_pdf()


def quote_pdf_filename(doc_number: str, service_name: str) -> str:
    """xlsx와 동일 패턴: 설계견적{doc_number}({service_name 안전 일부}).pdf"""
    safe = "".join(c for c in service_name if c not in r'\/:*?"<>|' + "\r\n")
    safe = safe.strip()[:30]
    return f"설계견적{doc_number}({safe}).pdf"
