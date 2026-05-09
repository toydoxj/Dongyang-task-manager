"""견적서 PDF 출력 — Jinja2 HTML 템플릿 + WeasyPrint.

xlsx 양식과 별개의 새 디자인. A4 1페이지에 회사 정보·서명란까지 포함.
시스템 의존성(cairo/pango/fonts-nanum)은 Dockerfile에서 install.

xlsx의 양식 보존 책임에서 분리되어 디자인 자유도가 높음 — 향후 양식 변경
시 templates/quote_template.html만 수정.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

from app.services.quote_calculator import QuoteType

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_LOGO_PATH = _TEMPLATE_DIR / "dongyang_logo.svg"
_SEAL_PATH = _TEMPLATE_DIR / "seal.png"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


# PDF 헤더 제목 — quote_type별 고정 라벨. CUSTOM은 input.custom_title 사용.
_TITLE_MAP: dict[QuoteType, str] = {
    QuoteType.STRUCT_DESIGN: "구조설계용역견적서",
    QuoteType.STRUCT_REVIEW: "구조검토용역견적서",
    QuoteType.PERF_SEISMIC: "성능기반내진설계용역견적서",
    QuoteType.INSPECTION_REGULAR: "정기안전점검 견적서",
    QuoteType.INSPECTION_DETAIL: "정밀점검 견적서",
    QuoteType.INSPECTION_DIAGNOSIS: "정밀안전진단 견적서",
    QuoteType.INSPECTION_BMA: "건축물관리법점검 견적서",
    QuoteType.SEISMIC_EVAL: "내진성능평가 견적서",
    QuoteType.REINFORCEMENT_DESIGN: "내진보강설계 견적서",
    QuoteType.THIRD_PARTY_REVIEW: "3자검토 견적서",
    QuoteType.SUPERVISION: "구조감리용역견적서",
    QuoteType.FIELD_SUPPORT: "현장기술지원용역견적서",
    QuoteType.CUSTOM: "견적서",  # custom_title이 있으면 그것 사용
}

# 파일명 prefix — xlsx 운영 파일명 패턴과 일치
_FILENAME_PREFIX_MAP: dict[QuoteType, str] = {
    QuoteType.STRUCT_DESIGN: "설계견적",
    QuoteType.STRUCT_REVIEW: "검토견적",
    QuoteType.PERF_SEISMIC: "성능내진견적",
    QuoteType.INSPECTION_REGULAR: "정기점검견적",
    QuoteType.INSPECTION_DETAIL: "정밀점검견적",
    QuoteType.INSPECTION_DIAGNOSIS: "정밀진단견적",
    QuoteType.INSPECTION_BMA: "건축물관리법점검견적",
    QuoteType.SEISMIC_EVAL: "내진성능평가견적",
    QuoteType.REINFORCEMENT_DESIGN: "내진보강설계견적",
    QuoteType.THIRD_PARTY_REVIEW: "3자검토견적",
    QuoteType.SUPERVISION: "구조감리견적",
    QuoteType.FIELD_SUPPORT: "현장지원견적",
    QuoteType.CUSTOM: "견적",
}


def _resolve_quote_type(value: str) -> QuoteType:
    """저장된 한글 문자열을 QuoteType으로. 빈 값/미지정은 STRUCT_DESIGN fallback."""
    if not value:
        return QuoteType.STRUCT_DESIGN
    try:
        return QuoteType(value)
    except ValueError:
        return QuoteType.STRUCT_DESIGN


def _read_logo_svg() -> str:
    """로고 SVG를 inline 삽입용 문자열로 반환. XML declaration은 제거."""
    if not _LOGO_PATH.exists():
        return ""
    text = _LOGO_PATH.read_text(encoding="utf-8")
    # HTML 안에서 처리되도록 XML declaration 제거
    if text.startswith("<?xml"):
        end = text.find("?>")
        if end != -1:
            text = text[end + 2 :].lstrip()
    return text


def _read_seal_data_uri() -> str:
    """도장 PNG를 data: URI로 inline (PDF에 자동 찍기). 파일 없으면 빈 문자열."""
    if not _SEAL_PATH.exists():
        return ""
    import base64

    data = _SEAL_PATH.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _krw(value: int | float | None) -> str:
    """₩ 표기 — None/0/빈 값은 빈 문자열로."""
    if value is None or value == 0:
        return ""
    return f"{int(value):,}원"


_env.filters["krw"] = _krw


def build_quote_pdf(
    form_data: dict[str, Any],
    *,
    doc_number: str = "",
    author_name: str = "",
    author_position: str = "",
) -> bytes:
    """form_data['input'] + ['result']를 quote_template.html로 렌더링 → PDF bytes.

    author_name/author_position은 헤더 doc-meta에 '작성자 : 이름 직급' 형식으로 표시.
    빈 값이면 작성자 라인 자체를 숨김.
    """
    template = _env.get_template("quote_template.html")
    inp = form_data.get("input") or {}
    result = form_data.get("result") or {}

    # 헤더 제목 — quote_type 별 고정 라벨, CUSTOM이면 custom_title 우선
    qtype = _resolve_quote_type(inp.get("quote_type", ""))
    custom_title = (inp.get("custom_title") or "").strip()
    quote_title = (
        custom_title
        if qtype is QuoteType.CUSTOM and custom_title
        else _TITLE_MAP[qtype]
    )

    html = template.render(
        doc_number=doc_number,
        input=inp,
        result=result,
        today=date.today().strftime("%Y. %m. %d"),
        logo_svg=_read_logo_svg(),
        seal_data_uri=_read_seal_data_uri(),
        author_name=author_name,
        author_position=author_position,
        quote_title=quote_title,
    )
    return HTML(string=html).write_pdf()


def build_bundle_cover_pdf(
    sections: list[dict[str, Any]],
    *,
    parent_name: str = "",
    parent_doc_number: str = "",
    author_name: str = "",
    author_position: str = "",
    parent_meta: dict[str, Any] | None = None,
    show_total: bool = True,
) -> bytes:
    """통합 PDF 첫 페이지 갑지(cover) — 영업 정보 + 견적 종합 표 + 총합.

    각 section의 input.quote_type을 업무내용으로, result.final을 금액으로 표기.
    수신처는 첫 견적의 recipient_company를 자동 채움.

    parent_meta dict (영업 정보 — 라우터에서 sale 필드 추출):
      code, assignees, submission_date, gross_floor_area,
      floors_above, floors_below, building_count
    """
    template = _env.get_template("quote_bundle_cover_template.html")
    rows: list[dict[str, Any]] = []
    total = 0
    recipient_company = ""
    for s in sections:
        form_data = s.get("form_data") or {}
        inp = form_data.get("input") or {}
        result = form_data.get("result") or {}
        amount = int(result.get("final") or 0)
        is_external = bool(s.get("is_external"))
        if is_external:
            # 외부 견적 — 사용자가 직접 입력한 service/amount 사용
            service = (s.get("service") or "외부 견적").strip()
        else:
            # 업무내용 — quote_type 우선. 기타이고 custom_title이 있으면 그걸 사용.
            qtype = (inp.get("quote_type") or "").strip()
            custom = (inp.get("custom_title") or "").strip()
            service = custom if (qtype == "기타" and custom) else (qtype or "—")
        rows.append(
            {
                "service": service,
                "doc_number": s.get("doc_number", "") or "",
                "amount": amount,
                "is_external": is_external,
                "attached_pdf_url": s.get("attached_pdf_url") or "",
                "attached_pdf_name": s.get("attached_pdf_name") or "",
            }
        )
        total += amount
        if not recipient_company:
            recipient_company = (inp.get("recipient_company") or "").strip()

    html = template.render(
        rows=rows,
        total=total,
        recipient_company=recipient_company,
        parent_name=parent_name,
        parent_doc_number=parent_doc_number,
        parent_meta=parent_meta or {},
        today=date.today().strftime("%Y. %m. %d"),
        logo_svg=_read_logo_svg(),
        seal_data_uri=_read_seal_data_uri(),
        author_name=author_name,
        author_position=author_position,
        show_total=show_total,
    )
    return HTML(string=html).write_pdf()


def build_quote_bundle_pdf(
    sections: list[dict[str, Any]],
    *,
    author_name: str = "",
    author_position: str = "",
    parent_name: str = "",
    parent_doc_number: str = "",
    parent_meta: dict[str, Any] | None = None,
    show_total: bool = True,
) -> bytes:
    """영업 내 다중 견적을 1 PDF로 묶음. 첫 페이지는 갑지(cover, 견적 종합 표
    + 총합), 후속 페이지는 자식 견적별 단일 PDF (build_quote_pdf 결과).

    각 section은 {form_data, doc_number} dict. 자식별로 build_quote_pdf()로
    PDF bytes 생성 후 pypdf로 concat. quote_template.html 변경 0줄로 회귀
    위험을 낮춘 디자인 (PR-G1).

    빈 견적 (form_data["input"]/["result"] 누락) section은 skip.
    """
    if not sections:
        raise ValueError("sections는 1건 이상 필요")

    writer = PdfWriter()

    # 1) 갑지 (PR-갑지) — 첫 페이지. parent meta는 라우터에서 sale.name/doc_number 전달
    cover_bytes = build_bundle_cover_pdf(
        sections,
        parent_name=parent_name,
        parent_doc_number=parent_doc_number,
        author_name=author_name,
        author_position=author_position,
        parent_meta=parent_meta,
        show_total=show_total,
    )
    cover_reader = PdfReader(io.BytesIO(cover_bytes))
    for page in cover_reader.pages:
        writer.add_page(page)

    # 2) 자식 견적별 PDF concat — 외부 견적(is_external)은 산출 데이터 없이
    # 갑지 row만 표시. PDF 첨부가 있으면 PR-EXT-2에서 concat.
    for section in sections:
        if section.get("is_external"):
            continue
        form_data = section.get("form_data") or {}
        if not form_data.get("input") or not form_data.get("result"):
            continue
        pdf_bytes = build_quote_pdf(
            form_data,
            doc_number=section.get("doc_number", "") or "",
            author_name=author_name,
            author_position=author_position,
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)

    if len(writer.pages) == 0:
        raise ValueError("렌더링할 견적이 없습니다 (모든 section에 form_data 누락)")

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def quote_bundle_pdf_filename(parent_doc_number: str, parent_name: str) -> str:
    """통합 PDF 파일명 — `통합견적{parent_doc}({parent_name 안전 일부}).pdf`."""
    safe = "".join(c for c in parent_name if c not in r'\/:*?"<>|' + "\r\n")
    safe = safe.strip()[:30]
    doc = parent_doc_number or "—"
    return f"통합견적{doc}({safe}).pdf"


def quote_pdf_filename(
    doc_number: str, service_name: str, quote_type: str = ""
) -> str:
    """{prefix}{doc_number}({service_name 안전 일부}).pdf — quote_type별 prefix.

    예: 설계견적26-01-007(...).pdf, 정기점검견적26-04-002(...).pdf
    """
    qtype = _resolve_quote_type(quote_type)
    prefix = _FILENAME_PREFIX_MAP[qtype]
    safe = "".join(c for c in service_name if c not in r'\/:*?"<>|' + "\r\n")
    safe = safe.strip()[:30]
    return f"{prefix}{doc_number}({safe}).pdf"
