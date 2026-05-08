"""영업(Sales) CRUD + 수주 전환 라우터.

read는 mirror_sales 테이블에서, write는 노션 → write-through로 mirror upsert.
사장이 운영하던 '견적서 작성 리스트' DB가 백엔드 미러링되어 있다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from urllib.parse import quote as url_quote

from app.db import get_db
from app.models import mirror as M
from app.models.employee import Employee
from app.models.auth import User
from app.models.project import Project, ProjectCreateRequest, project_create_to_props
from app.models.sale import (
    Sale,
    SaleCreateRequest,
    SaleListResponse,
    SaleUpdateRequest,
    sale_create_to_props,
    sale_update_to_props,
)
from app.security import get_current_user, require_admin
from app.services import sso_drive
from app.services.mirror_dto import sale_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.quote_calculator import (
    QuoteInput,
    QuoteResult,
    QuoteType,
    calculate,
)
from app.services.quote_code import next_quote_doc_number
from app.services.quote_forms import (
    format_doc_full,
    index_to_suffix,
    next_form_id,
    normalize_quote_forms,
    pack_quote_forms,
)
from app.services.quote_pdf import (
    build_quote_bundle_pdf,
    build_quote_pdf,
    quote_bundle_pdf_filename,
    quote_pdf_filename,
)
from app.services.sales_code import next_sales_code
from app.services.sales_probability import CONVERTIBLE_STAGES
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.sales")
router = APIRouter(prefix="/sales", tags=["sales"])

# /me '내 영업'에서 완료·종결 단계는 가시화 부담을 줄이기 위해 숨김.
# 제출 단계는 제출일 기준 60일 이내인 것만 노출 — 옛 제출 건 누적 방지.
_MINE_HIDDEN_STAGES: frozenset[str] = frozenset({"완료", "종결"})
_SUBMITTED_STAGE: str = "제출"
_SUBMITTED_VISIBLE_DAYS: int = 60


# ── 읽기 ──


@router.get("", response_model=SaleListResponse)
def list_sales(
    assignee: str | None = Query(default=None),
    kind: str | None = Query(default=None, description="수주영업|기술지원"),
    stage: str | None = Query(default=None),
    mine: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SaleListResponse:
    if mine:
        if not user.name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인 이름이 등록되어 있지 않아 mine 필터를 사용할 수 없습니다",
            )
        assignee = user.name

    stmt = select(M.MirrorSales).where(M.MirrorSales.archived.is_(False))
    if assignee:
        # contains(@>) — ARRAY GIN 인덱스 활용
        stmt = stmt.where(M.MirrorSales.assignees.contains([assignee]))  # type: ignore[attr-defined]
    if kind:
        stmt = stmt.where(M.MirrorSales.kind == kind)
    if stage:
        stmt = stmt.where(M.MirrorSales.stage == stage)
    if mine:
        # /me '내 영업' 가시화 정책: 완료·종결 숨김 + 제출은 60일 이내만.
        # 제출일이 비어 있는 제출 건은 데이터 누락 신호로 노출(PM에게 alert 효과).
        cutoff = date.today() - timedelta(days=_SUBMITTED_VISIBLE_DAYS)
        stmt = stmt.where(M.MirrorSales.stage.notin_(_MINE_HIDDEN_STAGES))
        stmt = stmt.where(
            or_(
                M.MirrorSales.stage != _SUBMITTED_STAGE,
                M.MirrorSales.submission_date.is_(None),
                M.MirrorSales.submission_date >= cutoff,
            )
        )
    # 최신 영업이 위로 — 등록일 역순. created_time이 None이면 last_edited_time fallback.
    stmt = stmt.order_by(M.MirrorSales.created_time.desc().nullslast())
    rows = db.execute(stmt).scalars().all()
    items = [sale_from_mirror(r) for r in rows]
    return SaleListResponse(items=items, count=len(items))


@router.get("/{page_id}", response_model=Sale)
def get_sale(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Sale:
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    return sale_from_mirror(row)


# ── 쓰기 ──


@router.post("", response_model=Sale, status_code=status.HTTP_201_CREATED)
async def create_sale(
    body: SaleCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    db_id = get_settings().notion_db_sales
    if not db_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="NOTION_DB_SALES 미설정",
        )
    if not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="견적서명 필수"
        )

    # 본인을 자동 담당자로 추가 (이미 담당자 list에 없을 때만)
    if user.name and user.name not in body.assignees:
        body = body.model_copy(update={"assignees": [*body.assignees, user.name]})

    # 영업코드 자동 부여 (빈 값일 때만 — 명시적으로 지정한 경우 그 값 유지).
    # advisory lock은 현재 트랜잭션 종료 시 자동 해제이므로 db.commit() 시점까지 유효.
    if not body.code:
        body = body.model_copy(update={"code": next_sales_code(db)})

    # 견적서 모드 — quote_form_data가 있는데 문서번호 미지정이면 자동 부여
    # ({YY}-{CC}-{NNN}, CC = 견적서 종류 분류 코드. quote_type은 form input
    # 또는 body.quote_type에서 결정, 빈 값은 구조설계 fallback)
    if body.quote_form_data and not body.quote_doc_number:
        qtype_val = (
            body.quote_type
            or (body.quote_form_data.get("input") or {}).get("quote_type")
            or ""
        )
        body = body.model_copy(
            update={"quote_doc_number": next_quote_doc_number(db, qtype_val)}
        )

    page = await notion.create_page(db_id, sale_create_to_props(body))
    get_sync().upsert_page("sales", page)

    # quote_form_data는 노션에 저장 불가 (JSONB). mirror_sales에만 별도 UPDATE.
    if body.quote_form_data:
        from sqlalchemy import update as sa_update

        new_page_id = page.get("id", "")
        db.execute(
            sa_update(M.MirrorSales)
            .where(M.MirrorSales.page_id == new_page_id)
            .values(quote_form_data=body.quote_form_data)
        )

    db.commit()  # advisory lock 해제 + mirror upsert 커밋
    return Sale.from_notion_page(page)


# ── 견적서 산출 미리보기 (저장 없음) ──


@router.post("/quote/preview", response_model=QuoteResult)
def preview_quote(
    body: QuoteInput,
    _user: User = Depends(get_current_user),
) -> QuoteResult:
    """견적서 입력 → 산출 결과만 반환 (저장 X). 프론트의 실시간 산출 패널용."""
    return calculate(body)


# ── 영업당 다중 견적서 CRUD (PR-M1) ──


class QuoteFormResponse(BaseModel):
    """영업 내 단일 견적서 form 응답 — quote_form_data["forms"] 항목 1건."""

    id: str
    doc_number: str   # 분류별 sequence ("26-04-001"). 외부 견적은 빈 값.
    suffix: str       # 영업 내 견적 인덱스 영문 ("A", "B", "AA", ...)
    full_doc: str     # doc_number + suffix ("26-04-001A")
    input: dict
    result: dict
    # 외부 견적 (PR-EXT) — 외주사 견적을 영업 묶음에 포함. 산출 X, 금액만.
    is_external: bool = False
    service: str = ""               # 외부 업무내용 (외부면 PDF 표·갑지 표시용)
    amount: float = 0               # 외부 금액 (result.final로도 보관, 갑지 합산)
    attached_pdf_url: str = ""      # 첨부 PDF web url (PR-EXT-2 Drive upload)
    attached_pdf_name: str = ""     # 첨부 파일명 (표시용)
    attached_pdf_file_id: str = ""  # WORKS Drive file_id (backend download용)


class ExternalQuoteRequest(BaseModel):
    """외부 견적 추가/수정 요청 — 산출 없이 업무내용 + 금액만."""

    service: str
    amount: float = Field(default=0, ge=0)


def _next_quote_suffix(forms: list[dict]) -> str:
    """기존 견적 list의 max suffix 다음 값. 삭제 후 hole 발생해도 max+1 보장."""

    def _suffix_to_index(s: str) -> int:
        idx = 0
        for c in s:
            if not ("A" <= c <= "Z"):
                return -1
            idx = idx * 26 + (ord(c) - ord("A") + 1)
        return idx - 1

    max_idx = max(
        (_suffix_to_index(f.get("suffix", "")) for f in forms),
        default=-1,
    )
    return index_to_suffix(max_idx + 1)


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


def _form_to_response(form: dict) -> QuoteFormResponse:
    return QuoteFormResponse(
        id=form.get("id", ""),
        doc_number=form.get("doc_number", ""),
        suffix=form.get("suffix", ""),
        full_doc=format_doc_full(form.get("doc_number", ""), form.get("suffix", "")),
        input=form.get("input") or {},
        result=form.get("result") or {},
        is_external=bool(form.get("is_external")),
        service=form.get("service") or "",
        amount=float(form.get("amount") or 0),
        attached_pdf_url=form.get("attached_pdf_url") or "",
        attached_pdf_name=form.get("attached_pdf_name") or "",
        attached_pdf_file_id=form.get("attached_pdf_file_id") or "",
    )


@router.get("/{page_id}/quotes", response_model=list[QuoteFormResponse])
def list_sale_quotes(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QuoteFormResponse]:
    """영업의 모든 견적 list. 옛 단일 schema는 자동 wrap (PR-M0 helper)."""
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    return [_form_to_response(f) for f in forms]


@router.post(
    "/{page_id}/quotes",
    response_model=QuoteFormResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_sale_quote(
    page_id: str,
    body: QuoteInput,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """영업에 견적 1건 추가. 분류별 sequence는 advisory lock으로 자동 부여,
    영업 내 suffix는 기존 견적의 max + 1.

    영업 한 건에 두 번째 견적 추가 시 sequence는 003 같은 다음 값, suffix는 B.
    삭제 후 hole 발생해도 새 견적은 max+1 (기존 doc_number 안정성 우선).
    """
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )

    # 분류별 sequence 발급 (advisory lock)
    qtype_val = body.quote_type if body.quote_type else ""
    new_doc = next_quote_doc_number(db, qtype_val)
    new_suffix = _next_quote_suffix(forms)
    result = calculate(body)

    new_form = {
        "id": next_form_id(),
        "doc_number": new_doc,
        "suffix": new_suffix,
        "input": body.model_dump(),
        "result": result.model_dump(),
    }
    forms.append(new_form)

    # 첫 견적이면 mirror_sales.quote_doc_number도 set (legacy view용)
    update_values: dict = {"quote_form_data": pack_quote_forms(forms)}
    if not row.quote_doc_number:
        update_values["quote_doc_number"] = format_doc_full(new_doc, new_suffix)

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(**update_values)
    )
    db.commit()

    return _form_to_response(new_form)


@router.patch(
    "/{page_id}/quotes/{quote_id}",
    response_model=QuoteFormResponse,
)
def update_sale_quote(
    page_id: str,
    quote_id: str,
    body: QuoteInput,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """기존 견적의 input·result만 수정. doc_number/suffix는 보존
    (외부 발송된 doc 변경되면 사장 운영 혼란)."""
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    target_idx = next(
        (i for i, f in enumerate(forms) if f.get("id") == quote_id), -1
    )
    if target_idx < 0:
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")

    result = calculate(body)
    forms[target_idx] = {
        **forms[target_idx],
        "input": body.model_dump(),
        "result": result.model_dump(),
    }

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(forms))
    )
    db.commit()

    return _form_to_response(forms[target_idx])


@router.delete("/{page_id}/quotes/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale_quote(
    page_id: str,
    quote_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """견적 삭제. suffix는 재할당 안 함 (기존 doc_number 안정성)."""
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    new_forms = [f for f in forms if f.get("id") != quote_id]
    if len(new_forms) == len(forms):
        raise HTTPException(status_code=404, detail="견적을 찾을 수 없습니다")

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(new_forms))
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 외부 견적 (PR-EXT) — 외주사 견적을 영업 묶음에 포함. 산출 X, 금액만. ──


@router.post(
    "/{page_id}/quotes/external",
    response_model=QuoteFormResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_external_quote(
    page_id: str,
    body: ExternalQuoteRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """외부 견적 추가 — 산출 X, 갑지에만 row로 표시.

    is_external=True flag로 일반 견적과 구별. doc_number는 빈값 (외부 회사가
    발급한 외부 문서이므로 사장 sequence 적용 X). suffix만 영업 내 인덱스 부여.
    PDF 첨부는 PR-EXT-2 (별 라우터)에서 추가.
    """
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    new_suffix = _next_quote_suffix(forms)
    new_form = {
        "id": next_form_id(),
        "doc_number": "",
        "suffix": new_suffix,
        "is_external": True,
        "service": body.service,
        "amount": body.amount,
        # 갑지 합산은 result.final 사용 — 일관성 위해 final에도 amount 보관
        "input": {},
        "result": {"final": body.amount},
    }
    forms.append(new_form)

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(forms))
    )
    db.commit()
    return _form_to_response(new_form)


@router.post(
    "/{page_id}/quotes/external/{quote_id}/attach-pdf",
    response_model=QuoteFormResponse,
)
async def attach_external_pdf(
    page_id: str,
    quote_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """외부 견적의 첨부 PDF를 WORKS Drive [견적서]/{YYYY}년/ 폴더에 업로드 →
    form.attached_pdf_url/name/file_id 갱신 (PR-EXT-2).

    파일명에 "외부_" prefix + 영업코드 + service 일부 자동 추가. 통합 PDF
    다운로드 시 attached_pdf_url을 갑지 표에서 hyperlink로 노출.
    """
    from sqlalchemy import update as sa_update

    settings_ = get_settings()
    if not settings_.works_drive_enabled:
        raise HTTPException(
            status_code=503,
            detail="WORKS Drive 통합이 비활성화되어 있습니다.",
        )
    if not settings_.works_drive_quote_root_folder_id:
        raise HTTPException(
            status_code=503,
            detail="견적서 저장 폴더 미설정 (WORKS_DRIVE_QUOTE_ROOT_FOLDER_ID)",
        )
    quote_settings = settings_
    if settings_.works_drive_quote_sharedrive_id:
        quote_settings = settings_.model_copy(
            update={
                "works_drive_sharedrive_id": settings_.works_drive_quote_sharedrive_id
            }
        )

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    target_idx = next(
        (i for i, f in enumerate(forms) if f.get("id") == quote_id), -1
    )
    if target_idx < 0 or not forms[target_idx].get("is_external"):
        raise HTTPException(status_code=404, detail="외부 견적을 찾을 수 없습니다")

    # 1. 파일 read
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(raw) > 50 * 1024 * 1024:  # 50MB cap
        raise HTTPException(status_code=413, detail="파일 크기 50MB 초과")

    # 2. 파일명 정책: 외부_{영업코드}_{service 안전한 30자}.{확장자}
    target_form = forms[target_idx]
    service = (target_form.get("service") or "외부견적").strip()
    safe_service = "".join(c for c in service if c not in r'\/:*?"<>|' + "\r\n")[:30].strip()
    sale_code = (row.code or "no-code").replace("-", "")
    orig_name = file.filename or "external.pdf"
    ext = orig_name.rsplit(".", 1)[-1] if "." in orig_name else "pdf"
    upload_filename = f"외부_{sale_code}_{safe_service}.{ext}"

    # 3. {YYYY}년 폴더 ensure
    year_yyyy = datetime.now(_KST).year
    try:
        year_folder_id, _ = await sso_drive.ensure_quote_year_folder(
            year_yyyy, settings=quote_settings
        )
    except sso_drive.DriveError as exc:
        logger.exception("외부 견적 PDF 연도 폴더 ensure 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 폴더 준비 실패: {exc}"
        ) from exc

    # 4. PDF upload
    try:
        meta = await sso_drive.upload_file(
            parent_file_id=year_folder_id,
            file_name=upload_filename,
            content=raw,
            content_type=file.content_type or "application/pdf",
            settings=quote_settings,
        )
    except sso_drive.DriveError as exc:
        logger.exception("외부 견적 PDF Drive 업로드 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 업로드 실패: {exc}"
        ) from exc

    file_id = meta.get("fileId") or ""
    web_url = sso_drive.build_file_web_url(
        file_id, meta.get("resourceLocation")
    )

    # 5. form 갱신
    forms[target_idx] = {
        **target_form,
        "attached_pdf_url": web_url,
        "attached_pdf_name": upload_filename,
        "attached_pdf_file_id": file_id,
    }
    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(forms))
    )
    db.commit()
    return _form_to_response(forms[target_idx])


@router.patch(
    "/{page_id}/quotes/external/{quote_id}",
    response_model=QuoteFormResponse,
)
def update_external_quote(
    page_id: str,
    quote_id: str,
    body: ExternalQuoteRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """외부 견적 service/amount 수정. 첨부 PDF는 보존."""
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")

    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    target_idx = next(
        (i for i, f in enumerate(forms) if f.get("id") == quote_id), -1
    )
    if target_idx < 0 or not forms[target_idx].get("is_external"):
        raise HTTPException(status_code=404, detail="외부 견적을 찾을 수 없습니다")

    forms[target_idx] = {
        **forms[target_idx],
        "service": body.service,
        "amount": body.amount,
        "result": {"final": body.amount},
    }
    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(forms))
    )
    db.commit()
    return _form_to_response(forms[target_idx])


@router.get("/quote/types")
def list_quote_types(
    _user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    """견적서 종류 enum + 한글 라벨. frontend select 옵션용.

    value/label 모두 한글 동일 (enum 값이 그대로 노션 select option name).
    """
    return [{"value": t.value, "label": t.value} for t in QuoteType]


# ── 견적서 PDF 다운로드 ──


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
                "attached_pdf_url": form.get("attached_pdf_url") or "",
                "attached_pdf_file_id": form.get("attached_pdf_file_id") or "",
            }
        )
    return sections


@router.get("/{page_id}/quote-bundle.pdf")
def download_quote_bundle_pdf(
    page_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """영업 1건의 견적 N개를 1 PDF로 묶어 다운로드 (PR-M4a 이후).

    영업 안에서 견적을 N개 작성한 경우 (PR-M0~M3 모델) 모두 합산해 page_break
    분리된 단일 PDF 생성. 견적이 1개여도 동작.
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

_KST = timezone(timedelta(hours=9))


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


@router.patch("/{page_id}", response_model=Sale)
async def update_sale(
    page_id: str,
    body: SaleUpdateRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    page = await notion.update_page(page_id, sale_update_to_props(body))
    get_sync().upsert_page("sales", page)

    # quote_form_data는 노션에 저장 불가 (JSONB) — mirror_sales에만 별도 UPDATE.
    # POST 흐름과 동일 패턴.
    if body.quote_form_data is not None:
        from sqlalchemy import update as sa_update

        db.execute(
            sa_update(M.MirrorSales)
            .where(M.MirrorSales.page_id == page_id)
            .values(quote_form_data=body.quote_form_data)
        )
        db.commit()

    sale = Sale.from_notion_page(page)
    # 응답에도 갱신된 quote_form_data 포함 (frontend가 즉시 prefill)
    if body.quote_form_data is not None:
        sale.quote_form_data = body.quote_form_data
    else:
        row = db.get(M.MirrorSales, page_id)
        if row is not None:
            sale.quote_form_data = row.quote_form_data or {}
    return sale


@router.delete("/{page_id}")
async def archive_sale(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """노션 페이지를 archive (soft delete). 노션은 영구 삭제 없음."""
    row = db.get(M.MirrorSales, page_id)
    if row is None:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    await asyncio.to_thread(
        notion._client.pages.update, page_id=page_id, archived=True
    )
    notion.clear_cache()
    get_sync().archive_page("sales", page_id)
    return {"status": "archived", "page_id": page_id}


# ── 수주 전환 ──


@router.post("/{page_id}/convert", response_model=Project)
async def convert_to_project(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Project:
    """영업 → 메인 프로젝트 DB 페이지 생성 + sale.converted_project_id 채움.

    검증:
    - 영업 건 존재 + 미archived
    - kind = 수주영업 (기술지원은 후속 수주영업 sale을 별도 생성하는 흐름)
    - stage in {우선협상, 낙찰}
    - converted_project_id 비어있음 (멱등성 — 두 번 변환 시 409)
    - name 비어있지 않음
    """
    settings = get_settings()
    if not settings.notion_db_projects:
        raise HTTPException(
            status_code=500, detail="NOTION_DB_PROJECTS 미설정"
        )

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    sale = sale_from_mirror(row)

    if sale.kind != "수주영업":
        raise HTTPException(
            status_code=400,
            detail="수주영업 단계의 영업만 프로젝트로 전환 가능합니다",
        )
    if sale.stage not in CONVERTIBLE_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"{', '.join(sorted(CONVERTIBLE_STAGES))} 단계의 영업만 전환 가능합니다",
        )
    if sale.converted_project_id:
        raise HTTPException(
            status_code=409,
            detail="이미 프로젝트로 전환된 영업입니다",
        )
    if not sale.name.strip():
        raise HTTPException(status_code=400, detail="영업 이름이 비어있어 전환 불가")

    # 새 프로젝트 생성 (수주확정 stage). PLAN_PROGRESS_EVAL §3.1
    project_req = ProjectCreateRequest(
        name=sale.name,
        client_relation_ids=[sale.client_id] if sale.client_id else [],
        stage="진행중",  # 기존 운영 select. 미래에 PROGRESS_EVAL 도입 시 "수주확정"으로 변경
        assignees=list(sale.assignees),
        contract_amount=sale.estimated_amount,
    )
    new_page = await notion.create_page(
        settings.notion_db_projects, project_create_to_props(project_req)
    )
    get_sync().upsert_page("projects", new_page)
    new_project_id = new_page.get("id", "")
    logger.info(
        "sale → project 전환: 새 프로젝트 생성 sale=%s project=%s name=%s",
        page_id[:8],
        new_project_id[:8],
        sale.name,
    )

    # 영업 건 갱신: 단계=완료, 전환된 프로젝트 = new_project_id.
    # 부분 실패 — 새 프로젝트는 만들었는데 여기서 실패하면 sale의 converted_project_id가
    # 비어 있어 멱등성이 깨짐(재시도 시 중복 프로젝트 생성). 클라이언트에 상태를 명확히
    # 전달하고 운영자가 수동 정리할 수 있도록 502를 보내며 new_project_id를 노출한다.
    try:
        update_props: dict = {
            "단계": {"select": {"name": "완료"}},
            "전환된 프로젝트": {"relation": [{"id": new_project_id}]},
        }
        updated_sale_page = await notion.update_page(page_id, update_props)
        get_sync().upsert_page("sales", updated_sale_page)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "sale 갱신 실패 — 새 프로젝트는 생성됨. 운영자 수동 연결 필요. "
            "sale=%s project=%s",
            page_id[:8],
            new_project_id[:8],
        )
        raise HTTPException(
            status_code=502,
            detail=(
                f"새 프로젝트({new_project_id})는 생성되었으나 영업 건의 "
                "'전환된 프로젝트' 갱신에 실패했습니다. 노션에서 수동 연결 후 "
                "재시도하지 말고 운영자에게 알려주세요."
            ),
        ) from exc

    return Project.from_notion_page(new_page)


# ── 기존 진행 프로젝트에 수동 연결 ──


class LinkProjectRequest(BaseModel):
    project_id: str


@router.post("/{page_id}/link-project", response_model=Sale)
async def link_to_existing_project(
    page_id: str,
    body: LinkProjectRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    """이미 진행 중인 프로젝트에 영업을 수동 연결.

    /convert(신규 프로젝트 생성)와 다름 — 기존 mirror_projects의 프로젝트에 영업의
    `전환된 프로젝트` relation을 채워 넣고 단계를 `완료`로 갱신.

    검증:
    - 영업 미archived
    - kind = 수주영업 (기술지원은 후속 수주영업 sale을 별도 생성)
    - converted_project_id 비어 있음 (멱등성)
    - project_id가 mirror_projects에 존재 + 미archived
    """
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    sale = sale_from_mirror(row)

    if sale.kind != "수주영업":
        raise HTTPException(
            status_code=400,
            detail="수주영업 유형의 영업만 프로젝트에 연결 가능합니다",
        )
    if sale.converted_project_id:
        raise HTTPException(
            status_code=409,
            detail="이미 프로젝트에 연결된 영업입니다",
        )

    project_row = db.get(M.MirrorProject, body.project_id)
    if project_row is None or project_row.archived:
        raise HTTPException(
            status_code=404, detail="대상 프로젝트를 찾을 수 없습니다"
        )

    update_props: dict = {
        "단계": {"select": {"name": "완료"}},
        "전환된 프로젝트": {"relation": [{"id": body.project_id}]},
    }
    updated_page = await notion.update_page(page_id, update_props)
    get_sync().upsert_page("sales", updated_page)
    logger.info(
        "sale → 기존 프로젝트 연결: sale=%s project=%s",
        page_id[:8],
        body.project_id[:8],
    )
    return Sale.from_notion_page(updated_page)
