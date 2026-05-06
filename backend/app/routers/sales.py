"""영업(Sales) CRUD + 수주 전환 라우터.

read는 mirror_sales 테이블에서, write는 노션 → write-through로 mirror upsert.
사장이 운영하던 '견적서 작성 리스트' DB가 백엔드 미러링되어 있다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from urllib.parse import quote as url_quote

from app.db import get_db
from app.models import mirror as M
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
from app.services.quote_calculator import QuoteInput, QuoteResult, calculate
from app.services.quote_code import next_quote_doc_number
from app.services.quote_pdf import build_quote_pdf, quote_pdf_filename
from app.services.quote_xlsx import build_quote_xlsx, quote_filename
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

    # 견적서 모드 — quote_form_data가 있는데 문서번호 미지정이면 자동 부여 ({YY}-{MM}-{NNN})
    if body.quote_form_data and not body.quote_doc_number:
        body = body.model_copy(
            update={"quote_doc_number": next_quote_doc_number(db)}
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


# ── 견적서 xlsx 다운로드 ──


@router.get("/{page_id}/quote.xlsx")
def download_quote_xlsx(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """저장된 견적서 입력값으로 xlsx 양식 생성 → 첨부 다운로드."""
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    form_data = row.quote_form_data or {}
    if not form_data.get("input"):
        raise HTTPException(
            status_code=400,
            detail="이 영업 건에는 견적서 데이터가 없습니다 (견적서 탭으로 만든 영업만 다운로드 가능)",
        )

    xlsx_bytes = build_quote_xlsx(form_data, doc_number=row.quote_doc_number or "")
    filename = quote_filename(row.quote_doc_number or "no-doc", row.name or "견적서")
    # RFC 5987 — 한글 파일명 안전 인코딩
    encoded = url_quote(filename, safe="")
    return Response(
        content=xlsx_bytes,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"quote.xlsx\"; "
                f"filename*=UTF-8''{encoded}"
            )
        },
    )


@router.get("/{page_id}/quote.pdf")
def download_quote_pdf(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """저장된 견적서 입력값으로 PDF 생성 → 다운로드 (WeasyPrint, A4 1페이지)."""
    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    form_data = row.quote_form_data or {}
    if not form_data.get("input"):
        raise HTTPException(
            status_code=400,
            detail="이 영업 건에는 견적서 데이터가 없습니다 (견적서 탭으로 만든 영업만 다운로드 가능)",
        )

    pdf_bytes = build_quote_pdf(form_data, doc_number=row.quote_doc_number or "")
    filename = quote_pdf_filename(
        row.quote_doc_number or "no-doc", row.name or "견적서"
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


# ── 견적서 xlsx → WORKS Drive 자동 저장 ──


_KST = timezone(timedelta(hours=9))


@router.post("/{page_id}/quote/save-to-drive", response_model=Sale)
async def save_quote_to_drive(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    """견적서 xlsx 생성 → `공용 드라이브\\[견적서]\\{YYYY}년\\` 업로드 →
    노션 sale의 `견적서첨부` 컬럼에 web url 저장.

    `WORKS_DRIVE_ENABLED=false`거나 `WORKS_DRIVE_QUOTE_ROOT_FOLDER_ID` 미설정 시 503.
    같은 견적의 두 번째 호출은 폴더 idempotent + 파일명 suffix로 안전 (`(1)` 추가).
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
    # [업무관리]와 [견적서]가 별도 sharedrive인 경우 견적 흐름만 다른 sharedrive로 라우팅.
    # WORKS_DRIVE_QUOTE_SHAREDRIVE_ID 미설정이면 기존 동작과 동일.
    quote_settings = settings_
    if settings_.works_drive_quote_sharedrive_id:
        quote_settings = settings_.model_copy(
            update={"works_drive_sharedrive_id": settings_.works_drive_quote_sharedrive_id}
        )

    row = db.get(M.MirrorSales, page_id)
    if row is None or row.archived:
        raise HTTPException(status_code=404, detail="영업 건을 찾을 수 없습니다")
    form_data = row.quote_form_data or {}
    if not form_data.get("input"):
        raise HTTPException(
            status_code=400,
            detail="견적서 데이터가 없습니다 (견적서 탭으로 만든 영업만 Drive 저장 가능)",
        )

    # 1. xlsx 생성
    xlsx_bytes = build_quote_xlsx(form_data, doc_number=row.quote_doc_number or "")
    filename = quote_filename(row.quote_doc_number or "no-doc", row.name or "견적서")

    # 2. {YYYY}년 폴더 ensure (KST 기준)
    year_yyyy = datetime.now(_KST).year
    try:
        year_folder_id, _year_url = await sso_drive.ensure_quote_year_folder(
            year_yyyy, settings=quote_settings
        )
    except sso_drive.DriveError as exc:
        logger.exception("견적서 연도 폴더 ensure 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 폴더 준비 실패: {exc}"
        ) from exc

    # 3. 업로드
    try:
        meta = await sso_drive.upload_file(
            parent_file_id=year_folder_id,
            file_name=filename,
            content=xlsx_bytes,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            settings=quote_settings,
        )
    except sso_drive.DriveError as exc:
        logger.exception("견적서 xlsx Drive 업로드 실패")
        raise HTTPException(
            status_code=502, detail=f"WORKS Drive 업로드 실패: {exc}"
        ) from exc

    # 4. 노션 sale 갱신 — 견적서첨부 + 제출일 자동 채움 (둘 다 같은 update_page 호출로 처리)
    file_id = meta.get("fileId") or ""
    web_url = sso_drive.build_file_web_url(file_id, meta.get("resourceLocation"))
    if not web_url:
        logger.warning("Drive 업로드 OK but webUrl 산출 실패: %s", file_id)

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
    # 제출일이 비어 있으면 KST 기준 오늘 날짜 자동 채움 (사용자 입력 우선, 없으면 저장 시점).
    # 노션 update 성공 시 get_sync().upsert_page가 mirror_sales.submission_date도 함께 sync.
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

    # 최신 상태 반환
    row = db.get(M.MirrorSales, page_id)
    return sale_from_mirror(row) if row else Sale.from_notion_page({"id": page_id})


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
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> dict[str, str]:
    """노션 페이지를 archive (soft delete). admin 전용. 노션은 영구 삭제 없음."""
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
    _admin: User = Depends(require_admin),
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
    _admin: User = Depends(require_admin),
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
