"""영업(Sales) CRUD + 수주 전환 라우터.

read는 mirror_sales 테이블에서, write는 노션 → write-through로 mirror upsert.
사장이 운영하던 '견적서 작성 리스트' DB가 백엔드 미러링되어 있다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
# url_quote는 PR-CE에서 pdf.py로 이동

from app.db import get_db
from app.models import mirror as M
# Employee import는 PR-CE에서 pdf.py로 이동
from app.models.auth import User
# Project 관련 import는 PR-CD에서 link.py로 이동
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
# quote_pdf import (build_*/filename helpers)는 PR-CE에서 pdf.py로 이동
from app.services.sales_code import next_sales_code
# CONVERTIBLE_STAGES는 PR-CD에서 link.py로 이동
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.sales")
router = APIRouter(prefix="/sales", tags=["sales"])

# PR-CC: _KST는 line 1048에서 PDF section과 함께 정의됐으나, line 772 외부 견적
# attach endpoint도 사용하므로 상단으로 옮김 (PR-CE에서 PDF section을 pdf.py로
# 이동하면서).
_KST = timezone(timedelta(hours=9))

# PR-CC/CD/CE (Phase 4-J): sub-router include — 상위 router의 prefix(`/sales`)를
# 그대로 상속받음. sub-module은 prefix 없이 endpoint 정의.
from app.routers.sales import link as _link  # noqa: E402
from app.routers.sales import pdf as _pdf  # noqa: E402
from app.routers.sales import quote_meta as _quote_meta  # noqa: E402

router.include_router(_quote_meta.router)
router.include_router(_link.router)
router.include_router(_pdf.router)


async def _create_quote_task_for_sale(
    notion: NotionService, sale_row: M.MirrorSales, db: Session
) -> None:
    """첫 견적 추가 시 노션 task 자동 생성 — 영업당 1회.

    중복 방지: sales_ids에 이 영업 page_id가 연결된 active task가 이미 있으면 skip
    (idempotent). 노션 task DB에 "영업" relation 컬럼이 부재하면 422 발생할 수
    있으므로 실패는 logger.warn으로 흡수 (응답 흐름 유지).
    """
    existing = (
        db.query(M.MirrorTask.page_id)
        .filter(M.MirrorTask.archived.is_(False))
        .filter(M.MirrorTask.sales_ids.any(sale_row.page_id))
        .first()
    )
    if existing:
        return

    assignees = [a for a in (sale_row.assignees or []) if a]
    title_parts: list[str] = []
    if sale_row.code:
        title_parts.append(sale_row.code)
    title_parts.append("견적서 작성")
    if sale_row.name:
        title_parts.append(f"— {sale_row.name}")
    title = " ".join(title_parts)

    today_iso = date.today().isoformat()
    props: dict[str, Any] = {
        "내용": {"title": [{"text": {"content": title}}]},
        "분류": {"select": {"name": "영업(서비스)"}},
        "영업": {"relation": [{"id": sale_row.page_id}]},
        "상태": {"status": {"name": "시작 전"}},
        "기간": {"date": {"start": today_iso}},
    }
    if assignees:
        props["담당자"] = {"multi_select": [{"name": a} for a in assignees]}

    settings = get_settings()
    try:
        page = await notion.create_page(settings.notion_db_tasks, props)
        try:
            get_sync().upsert_page("tasks", page)
        except Exception as e:  # noqa: BLE001
            logger.warning("자동 quote task mirror upsert 실패: %s", e)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "자동 quote task 생성 실패 (영업 %s — 노션 task DB에 '영업' relation "
            "컬럼이 없으면 발생; 운영자가 노션 UI에서 직접 추가 필요): %s",
            sale_row.code or sale_row.page_id,
            e,
        )

# /me '내 영업'에서 완료·종결 단계는 가시화 부담을 줄이기 위해 숨김.
# 제출 단계는 제출일 기준 60일 이내인 것만 노출 — 옛 제출 건 누적 방지.
_MINE_HIDDEN_STAGES: frozenset[str] = frozenset({"완료", "종결"})
_SUBMITTED_STAGE: str = "제출"
_SUBMITTED_VISIBLE_DAYS: int = 60


# ── 읽기 ──


# PR-EB (4-C 3차): list_sales pagination. PR-DZ list_projects 동일 패턴.
_LIST_MAX_LIMIT = 500


@router.get("", response_model=SaleListResponse)
def list_sales(
    assignee: str | None = Query(default=None),
    kind: str | None = Query(default=None, description="수주영업|기술지원"),
    stage: str | None = Query(default=None),
    mine: bool = Query(default=False),
    offset: int | None = Query(default=None, ge=0),
    limit: int | None = Query(default=None, ge=1, le=_LIST_MAX_LIMIT),
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
    # 최신 영업이 위로 — 등록일 역순 + page_id tie-breaker (결정론 보장).
    stmt = stmt.order_by(
        M.MirrorSales.created_time.desc().nullslast(),
        M.MirrorSales.page_id.asc(),
    )

    paged = offset is not None or limit is not None
    total: int | None = None
    if paged:
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(db.execute(count_stmt).scalar() or 0)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().all()
    items = [sale_from_mirror(r) for r in rows]
    return SaleListResponse(items=items, count=len(items), total=total)


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
    # frontend가 단일 schema {input, result}로 보내면 list-wrapped로 변환 후 저장
    # (그렇지 않으면 listSaleQuotes 호출 때마다 normalize_quote_forms가 새 uuid 생성
    #  → quote_id 매번 달라져 update/delete 라우터에서 "견적을 찾을 수 없습니다" 에러).
    if body.quote_form_data:
        from sqlalchemy import update as sa_update

        new_page_id = page.get("id", "")
        raw_fd = body.quote_form_data
        if "forms" not in raw_fd and "input" in raw_fd:
            # 단일 schema → list-wrapped (DB에 stable form id로 저장)
            wrapped = pack_quote_forms([
                {
                    "id": next_form_id(),
                    "doc_number": body.quote_doc_number or "",
                    "suffix": "A",
                    "input": raw_fd.get("input") or {},
                    "result": raw_fd.get("result") or {},
                }
            ])
        else:
            wrapped = raw_fd
        db.execute(
            sa_update(M.MirrorSales)
            .where(M.MirrorSales.page_id == new_page_id)
            .values(quote_form_data=wrapped)
        )

    db.commit()  # advisory lock 해제 + mirror upsert 커밋
    return Sale.from_notion_page(page)


# /quote/preview — PR-CF에서 sales/quote_meta.py로 이동


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
    vat_included: bool = False      # VAT 포함 여부 (외부 견적 — 갑지 라벨)
    attached_pdf_url: str = ""      # 첨부 PDF web url (PR-EXT-2 Drive upload)
    attached_pdf_name: str = ""     # 첨부 파일명 (표시용)
    attached_pdf_file_id: str = ""  # WORKS Drive file_id (backend download용)


class ExternalQuoteRequest(BaseModel):
    """외부 견적 추가/수정 요청 — 산출 없이 업무내용 + 금액만."""

    service: str
    amount: float = Field(default=0, ge=0)
    # VAT 포함/별도 — default False(VAT 별도). 갑지 금액 옆 표시.
    vat_included: bool = False


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


# _resolve_target_form / _form_to_pdf_data — PR-CE에서 routers/sales/pdf.py로 이동


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
        vat_included=bool(form.get("vat_included")),
        attached_pdf_url=form.get("attached_pdf_url") or "",
        attached_pdf_name=form.get("attached_pdf_name") or "",
        attached_pdf_file_id=form.get("attached_pdf_file_id") or "",
    )


async def _sync_sale_estimated_amount(
    db: Session,
    page_id: str,
    notion: NotionService,
) -> None:
    """영업 row의 estimated_amount를 모든 견적(일반+외부)의 final 합계로 갱신.
    mirror_sales + 노션 "견적금액" 둘 다 update. 견적 add/edit/delete 후 호출.

    PR-BZ (외부 리뷰 12.x #3): row-level lock으로 동시 호출 race 차단.
    두 명이 동시에 견적을 추가/수정해도 last-write-wins이 아닌 직렬 처리.
    노션 호출은 락 release 후 (외부 API latency가 락에 영향 X).
    """
    from sqlalchemy import select as sa_select
    from sqlalchemy import update as sa_update

    # SELECT ... FOR UPDATE — 동일 page_id의 동시 _sync 호출은 락 대기 후 직렬화.
    # SQLite(test)에서는 noop이라 운영(Postgres)에만 효과. 호출처 트랜잭션 commit
    # 이후이므로 quote_form_data는 항상 최신.
    row = db.execute(
        sa_select(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        db.rollback()
        return
    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    total = 0
    for f in forms:
        if f.get("is_external"):
            total += int(f.get("amount") or 0)
        else:
            result = f.get("result") or {}
            total += int(result.get("final") or 0)

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(estimated_amount=float(total))
    )
    db.commit()  # 락 release. 노션 update는 별도 트랜잭션 외부.

    try:
        updated = await notion.update_page(
            page_id, {"견적금액": {"number": total}}
        )
        get_sync().upsert_page("sales", updated)
    except Exception:  # noqa: BLE001
        logger.exception(
            "견적금액 노션 sync 실패 — 운영 수동 보정 필요 (page_id=%s)", page_id
        )


@router.get("/{page_id}/quotes", response_model=list[QuoteFormResponse])
def list_sale_quotes(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[QuoteFormResponse]:
    """영업의 모든 견적 list. 옛 단일 schema는 자동 wrap (PR-M0 helper) +
    DB에 list-wrapped로 lazy 마이그레이션 (다음 호출부터 stable form id 보장)."""
    from sqlalchemy import update as sa_update

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    forms = normalize_quote_forms(
        row.quote_form_data, legacy_doc_number=row.quote_doc_number or ""
    )
    # legacy 단일 schema → list-wrapped로 마이그레이션 (stable id)
    raw_fd = row.quote_form_data or {}
    if forms and "forms" not in raw_fd:
        db.execute(
            sa_update(M.MirrorSales)
            .where(M.MirrorSales.page_id == page_id)
            .values(quote_form_data=pack_quote_forms(forms))
        )
        db.commit()
    return [_form_to_response(f) for f in forms]


@router.post(
    "/{page_id}/quotes",
    response_model=QuoteFormResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_sale_quote(
    page_id: str,
    body: QuoteInput,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> QuoteFormResponse:
    """영업에 견적 1건 추가. 분류별 sequence는 advisory lock으로 자동 부여,
    영업 내 suffix는 기존 견적의 max + 1.

    영업 한 건에 두 번째 견적 추가 시 sequence는 003 같은 다음 값, suffix는 B.
    삭제 후 hole 발생해도 새 견적은 max+1 (기존 doc_number 안정성 우선).
    추가 후 영업 row의 견적금액(estimated_amount)을 합계로 자동 sync (mirror+노션).
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
    db.refresh(row)

    await _sync_sale_estimated_amount(db, page_id, notion)
    # 첫 견적이면 노션 task DB에 견적서 작성 task 자동 생성 (PR-W follow-up).
    # idempotent — 이미 sales_ids 연결된 task가 있으면 skip.
    await _create_quote_task_for_sale(notion, row, db)
    return _form_to_response(new_form)


@router.patch(
    "/{page_id}/quotes/{quote_id}",
    response_model=QuoteFormResponse,
)
async def update_sale_quote(
    page_id: str,
    quote_id: str,
    body: QuoteInput,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> QuoteFormResponse:
    """기존 견적의 input·result만 수정. doc_number/suffix는 보존
    (외부 발송된 doc 변경되면 사장 운영 혼란).
    수정 후 영업 row의 견적금액 자동 sync."""
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

    await _sync_sale_estimated_amount(db, page_id, notion)
    return _form_to_response(forms[target_idx])


class QuoteDocNumberRequest(BaseModel):
    """견적 문서번호 수동 변경 요청 — 사용자가 임의 doc_number로 override.
    빈 문자열 허용 (외부 견적처럼 doc 비우기). suffix는 보존됨.
    """

    doc_number: str = ""


@router.patch(
    "/{page_id}/quotes/{quote_id}/doc-number",
    response_model=QuoteFormResponse,
)
async def update_quote_doc_number(
    page_id: str,
    quote_id: str,
    body: QuoteDocNumberRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuoteFormResponse:
    """견적의 doc_number만 수동 수정 (advisory lock sequence와 무관).
    suffix/input/result는 보존. mirror_sales.quote_doc_number(첫 견적 표시용)도
    영업의 첫 견적이면 같이 갱신.
    """
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

    new_doc = body.doc_number.strip()
    forms[target_idx] = {**forms[target_idx], "doc_number": new_doc}

    update_values: dict = {"quote_form_data": pack_quote_forms(forms)}
    # 영업의 첫 견적이면 mirror_sales.quote_doc_number도 동기 (legacy view용)
    if target_idx == 0:
        update_values["quote_doc_number"] = format_doc_full(
            new_doc, forms[target_idx].get("suffix", "")
        )

    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(**update_values)
    )
    db.commit()
    return _form_to_response(forms[target_idx])


@router.delete("/{page_id}/quotes/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sale_quote(
    page_id: str,
    quote_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Response:
    """견적 삭제. suffix는 재할당 안 함 (기존 doc_number 안정성).
    삭제 후 영업 row의 견적금액 자동 sync."""
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
    await _sync_sale_estimated_amount(db, page_id, notion)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 외부 견적 (PR-EXT) — 외주사 견적을 영업 묶음에 포함. 산출 X, 금액만. ──


@router.post(
    "/{page_id}/quotes/external",
    response_model=QuoteFormResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_external_quote(
    page_id: str,
    body: ExternalQuoteRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> QuoteFormResponse:
    """외부 견적 추가 — 산출 X, 갑지에만 row로 표시.

    is_external=True flag로 일반 견적과 구별. doc_number는 빈값 (외부 회사가
    발급한 외부 문서이므로 사장 sequence 적용 X). suffix만 영업 내 인덱스 부여.
    PDF 첨부는 PR-EXT-2 (별 라우터)에서 추가. 추가 후 영업 견적금액 자동 sync.
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
        "vat_included": body.vat_included,
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
    await _sync_sale_estimated_amount(db, page_id, notion)
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
async def update_external_quote(
    page_id: str,
    quote_id: str,
    body: ExternalQuoteRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> QuoteFormResponse:
    """외부 견적 service/amount 수정. 첨부 PDF는 보존. 영업 견적금액 자동 sync."""
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
        "vat_included": body.vat_included,
        "result": {"final": body.amount},
    }
    db.execute(
        sa_update(M.MirrorSales)
        .where(M.MirrorSales.page_id == page_id)
        .values(quote_form_data=pack_quote_forms(forms))
    )
    db.commit()
    await _sync_sale_estimated_amount(db, page_id, notion)
    return _form_to_response(forms[target_idx])


# /quote/types — PR-CC에서 sales/quote_meta.py로 분리 (sub-router include는 파일 말미)


# PDF 4 endpoint(quote.pdf / quote-bundle.pdf / save-pdf-to-drive 2종) +
# _collect_bundle_sections helper — PR-CE에서 routers/sales/pdf.py로 이동

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
    # 단일 schema는 list-wrapped로 변환 (POST 흐름과 동일 — stable form id 보장).
    if body.quote_form_data is not None:
        from sqlalchemy import update as sa_update

        raw_fd = body.quote_form_data
        if "forms" not in raw_fd and "input" in raw_fd:
            # 영업 row의 기존 quote_doc_number 가져와 legacy_doc_number로 사용
            row_for_doc = db.get(M.MirrorSales, page_id)
            legacy_doc = row_for_doc.quote_doc_number if row_for_doc else ""
            wrapped = pack_quote_forms([
                {
                    "id": next_form_id(),
                    "doc_number": legacy_doc or "",
                    "suffix": "A",
                    "input": raw_fd.get("input") or {},
                    "result": raw_fd.get("result") or {},
                }
            ])
        else:
            wrapped = raw_fd
        db.execute(
            sa_update(M.MirrorSales)
            .where(M.MirrorSales.page_id == page_id)
            .values(quote_form_data=wrapped)
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


# 수주 전환 / by-project / link-project — PR-CD에서 routers/sales/link.py로 분리
