"""영업 ↔ 프로젝트 연결 endpoint.

PR-CD (Phase 4-J 2단계): __init__.py에서 link 관련 3 endpoint 분리.
- POST /{page_id}/convert — 신규 프로젝트 생성 + 영업 갱신
- GET /by-project/{project_id} — 프로젝트 → 영업 reverse lookup
- POST /{page_id}/link-project — 기존 프로젝트에 수동 연결

상위 router(`prefix="/sales"`)가 prefix 상속.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import mirror as M
from app.models.auth import User
from app.models.project import Project, ProjectCreateRequest, project_create_to_props
from app.models.sale import Sale
from app.security import get_current_user
from app.services.mirror_dto import sale_from_mirror
from app.services.notion import NotionService, get_notion
from app.services.sales_probability import CONVERTIBLE_STAGES
from app.services.sync import get_sync
from app.settings import get_settings

logger = logging.getLogger("api.sales.link")
router = APIRouter()


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


# ── 프로젝트 → 연결된 영업 reverse lookup ──


@router.get("/by-project/{project_id}", response_model=Sale | None)
def find_sale_by_project(
    project_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Sale | None:
    """프로젝트 id로 연결된 영업(Sale) 1건 reverse lookup.

    프로젝트 상세 페이지에서 "영업 상세" 버튼 노출용. converted_project_id
    indexed 컬럼으로 빠른 조회. 미archived 영업만. 없으면 null.
    """
    row = (
        db.query(M.MirrorSales)
        .filter(
            M.MirrorSales.converted_project_id == project_id,
            M.MirrorSales.archived.is_(False),
        )
        .first()
    )
    return sale_from_mirror(row) if row else None


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
