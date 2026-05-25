"""견적서 PDF endpoint — 다운로드 + WORKS Drive 자동 저장.

PR-CE (Phase 4-J 3단계): __init__.py에서 PDF 관련 4 endpoint + 3 helper 분리.
- GET /{page_id}/quote.pdf — 단일 견적 PDF 다운로드
- GET /{page_id}/quote-bundle.pdf — 통합 견적 PDF 다운로드
- POST /{page_id}/quote/save-pdf-to-drive — 단일 견적 PDF Drive 업로드
- POST /{page_id}/quote-bundle/save-pdf-to-drive — 통합 견적 PDF Drive 업로드

상위 router(`prefix="/sales"`)가 prefix 상속.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.employee import Employee
from app.models.sale import Sale
from app.security import get_current_user
from app.services import sso_drive
from app.services.mirror_dto import sale_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.quote_forms import format_doc_full, normalize_quote_forms
from app.services.quote_pdf import (
    build_quote_bundle_pdf,
    build_quote_pdf,
    quote_bundle_pdf_filename,
    quote_pdf_filename,
)
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.sales.pdf")
router = APIRouter()

_KST = timezone(timedelta(hours=9))


# ── helpers ──


def _resolve_target_form(forms: list[dict], quote_id: str) -> dict | None:
    """quote_id 명시 → 그 견적, 빈 값 → 첫 번째 (legacy 호환)."""
    if not forms:
        return None
    if quote_id:
        return next((f for f in forms if f.get("id") == quote_id), None)
    return forms[0]


def _form_to_pdf_data(form: dict) -> dict:
    """견적 form → build_quote_pdf 입력 형식 ({input, result})."""
    return {"input": form.get("input") or {}, "result": form.get("result") or {}}


def _collect_bundle_sections(
    db: Session, sale_id: str
) -> list[dict[str, object]]:
    """묶음 PDF용 sections 수집 — 영업 1건 안 견적 list 평탄화 (PR-M4a).

    영업당 다중 견적 모델 (PR-M0~M4) — 일반 견적 + 외부 견적 (PR-EXT).
    외부 견적은 input/result 비어 있어도 sections에 포함 (갑지 row 표시용).
    PDF concat에서 is_external은 build_quote_bundle_pdf가 skip.
    """
    sale = db.get(M.MirrorSales, sale_id)
    if sale is None or sale.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    sections: list[dict[str, object]] = []
    forms = normalize_quote_forms(
        sale.quote_form_data,
        legacy_doc_number=sale.quote_doc_number or "",
    )
    for form in forms:
        is_external = bool(form.get("is_external"))
        # 일반 견적: input/result 모두 필요. 외부 견적: 빈 input/result 허용.
        if not is_external and (not form.get("input") or not form.get("result")):
            continue
        sections.append(
            {
                "form_data": _form_to_pdf_data(form),
                "doc_number": format_doc_full(
                    form.get("doc_number", ""), form.get("suffix", "")
                ),
                "is_external": is_external,
                "service": form.get("service") or "",
                "amount": float(form.get("amount") or 0),
                "vat_included": bool(form.get("vat_included")),
                "attached_pdf_url": form.get("attached_pdf_url") or "",
                "attached_pdf_file_id": form.get("attached_pdf_file_id") or "",
            }
        )
    return sections


# ── 단일 견적 PDF 다운로드 ──


@router.get("/{page_id}/quote.pdf")
def download_quote_pdf(
    page_id: str,
    quote_id: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """영업의 단일 견적 PDF 다운로드 (WeasyPrint, A4).

    quote_id query param: 영업 내 견적 list에서 lookup. 빈 값이면 첫 견적
    (legacy 단일 견적 호환). 옛 quote_form_data 단일 schema는 PR-M0 helper
    로 자동 wrap 후 첫 form 사용.
    """
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    target = _resolve_target_form(forms, quote_id)
    if target is None or not target.get("input"):
        raise HTTPException(
            status_code=404 if quote_id else 400,
            detail=(
                "견적을 찾을 수 없습니다"
                if quote_id
                else "이 영업 건에는 견적서 데이터가 없습니다"
            ),
        )

    full_doc = format_doc_full(
        target.get("doc_number", ""), target.get("suffix", "")
    )
    qtype = target.get("input", {}).get("quote_type") or row.quote_type or ""

    employee = (
        db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    )
    author_name = (employee.name if employee else "") or user.name or user.username
    author_position = employee.position if employee else ""

    pdf_bytes = build_quote_pdf(
        _form_to_pdf_data(target),
        doc_number=full_doc,
        author_name=author_name,
        author_position=author_position,
    )
    filename = quote_pdf_filename(
        full_doc or "no-doc",
        row.name or "견적서",
        qtype,
    )
    encoded = url_quote(filename, safe="")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"quote.pdf\"; "
                f"filename*=UTF-8''{encoded}"
            )
        },
    )


# ── 통합 견적서 PDF 다운로드 (영업 내 다중 견적 묶음, PR-M4a) ──


@router.get("/{page_id}/quote-bundle.pdf")
def download_quote_bundle_pdf(
    page_id: str,
    show_total: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """영업 1건의 견적 N개를 1 PDF로 묶어 다운로드 (PR-M4a 이후).

    영업 안에서 견적을 N개 작성한 경우 (PR-M0~M3 모델) 모두 합산해 page_break
    분리된 단일 PDF 생성. 견적이 1개여도 동작.

    show_total: 갑지(첫 페이지)의 견적가 + 합계 row 표시 여부 (default True).
    """
    sale = db.get(M.MirrorSales, page_id)
    if sale is None or sale.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    sections = _collect_bundle_sections(db, page_id)
    if not sections:
        raise HTTPException(
            status_code=400,
            detail="이 영업에는 견적이 없습니다",
        )

    employee = (
        db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    )
    author_name = (employee.name if employee else "") or user.name or user.username
    author_position = employee.position if employee else ""

    pdf_bytes = build_quote_bundle_pdf(
        sections,
        author_name=author_name,
        author_position=author_position,
        parent_name=sale.name or "",
        parent_doc_number=sale.quote_doc_number or "",
        parent_meta={
            "code": sale.code or "",
            "assignees": list(sale.assignees or []),
            "submission_date": (
                sale.submission_date.isoformat() if sale.submission_date else ""
            ),
            "gross_floor_area": sale.gross_floor_area,
            "floors_above": sale.floors_above,
            "floors_below": sale.floors_below,
            "building_count": sale.building_count,
        },
        show_total=show_total,
    )
    filename = quote_bundle_pdf_filename(
        sale.quote_doc_number or "no-doc",
        sale.name or "통합견적",
    )
    encoded = url_quote(filename, safe="")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"quote-bundle.pdf\"; "
                f"filename*=UTF-8''{encoded}"
            )
        },
    )


# ── 견적서 PDF → WORKS Drive 자동 저장 ──


@router.post("/{page_id}/quote/save-pdf-to-drive", response_model=Sale)
async def save_quote_pdf_to_drive(
    page_id: str,
    quote_id: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    """단일 견적 PDF → `공용 드라이브\\[견적서]\\{YYYY}년\\` 업로드 →
    노션 sale의 `견적서첨부` 컬럼에 web url 저장.

    quote_id query: 영업 내 견적 list에서 lookup. 빈 값이면 첫 견적.
    `WORKS_DRIVE_ENABLED=false`거나 `WORKS_DRIVE_QUOTE_ROOT_FOLDER_ID` 미설정 시 503.
    """
    settings_ = get_settings()
    if not settings_.works_drive_enabled:
        raise HTTPException(
            status_code=503,
            detail="WORKS Drive 통합이 비활성화되어 있습니다 (WORKS_DRIVE_ENABLED=false).",
        )
    if not settings_.works_drive_quote_root_folder_id:
        raise HTTPException(
            status_code=503,
            detail="견적서 저장 폴더가 설정되지 않았습니다 (WORKS_DRIVE_QUOTE_ROOT_FOLDER_ID 미설정).",
        )
    quote_settings = settings_
    if settings_.works_drive_quote_sharedrive_id:
        quote_settings = settings_.model_copy(
            update={"works_drive_sharedrive_id": settings_.works_drive_quote_sharedrive_id}
        )

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    target = _resolve_target_form(forms, quote_id)
    if target is None or not target.get("input"):
        raise HTTPException(
            status_code=404 if quote_id else 400,
            detail=(
                "견적을 찾을 수 없습니다"
                if quote_id
                else "견적서 데이터가 없습니다 (견적서 탭으로 만든 영업만 Drive 저장 가능)"
            ),
        )

    full_doc = format_doc_full(
        target.get("doc_number", ""), target.get("suffix", "")
    )
    qtype = target.get("input", {}).get("quote_type") or row.quote_type or ""

    # 1. PDF 생성 (작성자는 다운로드 트리거한 user의 Employee 매핑)
    employee = (
        db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    )
    author_name = (employee.name if employee else "") or user.name or user.username
    author_position = employee.position if employee else ""

    pdf_bytes = build_quote_pdf(
        _form_to_pdf_data(target),
        doc_number=full_doc,
        author_name=author_name,
        author_position=author_position,
    )
    filename = quote_pdf_filename(
        full_doc or "no-doc",
        row.name or "견적서",
        qtype,
    )

    # 2. {YYYY}년 폴더 ensure
    year_yyyy = datetime.now(_KST).year
    try:
        year_folder_id, _ = await sso_drive.ensure_quote_year_folder(
            year_yyyy, settings=quote_settings
        )
    except sso_drive.DriveError as exc:
        logger.exception("견적서 연도 폴더 ensure 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 폴더 준비 실패: {exc}"
        ) from exc

    # 3. PDF 업로드
    try:
        meta = await sso_drive.upload_file(
            parent_file_id=year_folder_id,
            file_name=filename,
            content=pdf_bytes,
            content_type="application/pdf",
            settings=quote_settings,
        )
    except sso_drive.DriveError as exc:
        logger.exception("견적서 PDF Drive 업로드 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 업로드 실패: {exc}"
        ) from exc

    # 4. 노션 sale 갱신 — 견적서첨부 + 제출일 자동 채움
    file_id = meta.get("fileId") or ""
    web_url = sso_drive.build_file_web_url(file_id, meta.get("resourceLocation"))
    update_props: dict = {}
    if web_url:
        update_props["견적서첨부"] = {
            "files": [
                {
                    "name": filename,
                    "external": {"url": web_url},
                    "type": "external",
                }
            ]
        }
    if row.submission_date is None:
        today_kst = datetime.now(_KST).date().isoformat()
        update_props["제출일"] = {"date": {"start": today_kst}}

    if update_props:
        try:
            updated = await notion.update_page(page_id, update_props)
            get_sync().upsert_page("sales", updated)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Drive 업로드 후 노션 갱신 실패 — 운영 수동 보정 필요 (keys=%s)",
                list(update_props.keys()),
            )

    row = db.get(M.MirrorSales, page_id)
    return sale_from_mirror(row) if row else Sale.from_notion_page({"id": page_id})


# ── 통합 견적서 PDF → WORKS Drive 자동 저장 (PR-G2) ──


@router.post("/{page_id}/quote-bundle/save-pdf-to-drive", response_model=Sale)
async def save_quote_bundle_pdf_to_drive(
    page_id: str,
    show_total: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    """영업 1건의 견적 N개를 묶은 통합 PDF → `[견적서]\\{YYYY}년\\` 업로드 →
    노션 `통합견적서첨부` 컬럼에 web url 저장. 단일 견적 PDF (`견적서첨부`)는
    영향 없이 그대로 보존됨 (PR-M4a).
    """
    settings_ = get_settings()
    if not settings_.works_drive_enabled:
        raise HTTPException(
            status_code=503,
            detail="WORKS Drive 통합이 비활성화되어 있습니다 (WORKS_DRIVE_ENABLED=false).",
        )
    if not settings_.works_drive_quote_root_folder_id:
        raise HTTPException(
            status_code=503,
            detail="견적서 저장 폴더가 설정되지 않았습니다 (WORKS_DRIVE_QUOTE_ROOT_FOLDER_ID 미설정).",
        )
    quote_settings = settings_
    if settings_.works_drive_quote_sharedrive_id:
        quote_settings = settings_.model_copy(
            update={"works_drive_sharedrive_id": settings_.works_drive_quote_sharedrive_id}
        )

    sale = db.get(M.MirrorSales, page_id)
    if sale is None or sale.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    sections = _collect_bundle_sections(db, page_id)
    if not sections:
        raise HTTPException(
            status_code=400,
            detail="이 영업에는 견적이 없습니다",
        )

    # 1. 통합 PDF 생성
    employee = (
        db.query(Employee).filter(Employee.linked_user_id == user.id).first()
    )
    author_name = (employee.name if employee else "") or user.name or user.username
    author_position = employee.position if employee else ""
    pdf_bytes = build_quote_bundle_pdf(
        sections,
        author_name=author_name,
        author_position=author_position,
        parent_name=sale.name or "",
        parent_doc_number=sale.quote_doc_number or "",
        parent_meta={
            "code": sale.code or "",
            "assignees": list(sale.assignees or []),
            "submission_date": (
                sale.submission_date.isoformat() if sale.submission_date else ""
            ),
            "gross_floor_area": sale.gross_floor_area,
            "floors_above": sale.floors_above,
            "floors_below": sale.floors_below,
            "building_count": sale.building_count,
        },
        show_total=show_total,
    )
    filename = quote_bundle_pdf_filename(
        sale.quote_doc_number or "no-doc",
        sale.name or "통합견적",
    )

    # 2. {YYYY}년 폴더 ensure
    year_yyyy = datetime.now(_KST).year
    try:
        year_folder_id, _ = await sso_drive.ensure_quote_year_folder(
            year_yyyy, settings=quote_settings
        )
    except sso_drive.DriveError as exc:
        logger.exception("통합 견적서 연도 폴더 ensure 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 폴더 준비 실패: {exc}"
        ) from exc

    # 3. PDF 업로드
    try:
        meta = await sso_drive.upload_file(
            parent_file_id=year_folder_id,
            file_name=filename,
            content=pdf_bytes,
            content_type="application/pdf",
            settings=quote_settings,
        )
    except sso_drive.DriveError as exc:
        logger.exception("통합 견적서 PDF Drive 업로드 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 업로드 실패: {exc}"
        ) from exc

    # 4. parent 노션 row의 통합견적서첨부 컬럼 갱신
    file_id = meta.get("fileId") or ""
    web_url = sso_drive.build_file_web_url(file_id, meta.get("resourceLocation"))
    update_props: dict = {}
    if web_url:
        update_props["통합견적서첨부"] = {
            "files": [
                {
                    "name": filename,
                    "external": {"url": web_url},
                    "type": "external",
                }
            ]
        }

    if update_props:
        try:
            updated = await notion.update_page(page_id, update_props)
            get_sync().upsert_page("sales", updated)
        except Exception:  # noqa: BLE001
            logger.exception(
                "통합 PDF 업로드 후 노션 갱신 실패 — 운영 수동 보정 필요 (keys=%s)",
                list(update_props.keys()),
            )

    sale = db.get(M.MirrorSales, page_id)
    return sale_from_mirror(sale) if sale else Sale.from_notion_page({"id": page_id})
