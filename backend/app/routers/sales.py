"""영업(Sales) CRUD + 수주 전환 라우터.

read는 mirror_sales 테이블에서, write는 노션 → write-through로 mirror upsert.
사장이 운영하던 '견적서 작성 리스트' DB가 백엔드 미러링되어 있다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

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
from app.services.mirror_dto import sale_from_mirror
from app.services.notion import NotionService, get_notion
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
async def list_sales(
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
async def get_sale(
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

    page = await notion.create_page(db_id, sale_create_to_props(body))
    get_sync().upsert_page("sales", page)
    return Sale.from_notion_page(page)


@router.patch("/{page_id}", response_model=Sale)
async def update_sale(
    page_id: str,
    body: SaleUpdateRequest,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> Sale:
    page = await notion.update_page(page_id, sale_update_to_props(body))
    get_sync().upsert_page("sales", page)
    return Sale.from_notion_page(page)


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
