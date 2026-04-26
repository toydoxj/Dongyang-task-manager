"""/api/master-projects — 조회/수정/이미지. read는 mirror, write는 노션 + write-through."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import NotFoundError
from app.models import mirror as M
from app.models.auth import User
from app.security import get_current_user
from app.services import notion_props as P
from app.services.notion import NotionService, get_notion
from app.services.sync import get_sync

# 노션이 업로드를 받는 MIME 화이트리스트 (이미지)
_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # single_part upload 한도

router = APIRouter(prefix="/master-projects", tags=["master-projects"])


class SubProjectRef(BaseModel):
    id: str
    name: str = ""
    code: str = ""
    stage: str = ""


class MasterProject(BaseModel):
    id: str
    name: str = ""
    code: str = ""
    address: str = ""
    usage: list[str] = []
    structure: list[str] = []
    floors_above: int | None = None
    floors_below: int | None = None
    height: float | None = None
    area: float | None = None
    units: int | None = None
    high_rise: bool = False
    multi_use: bool = False
    special_structure: bool = False
    completed: bool = False
    special_types: list[str] = []
    sub_project_ids: list[str] = []
    sub_projects: list[SubProjectRef] = []
    url: str | None = None


class MasterProjectUpdate(BaseModel):
    """전체 필드 optional — 제공된 키만 업데이트."""

    name: str | None = None
    code: str | None = None
    address: str | None = None
    usage: list[str] | None = None
    structure: list[str] | None = None
    floors_above: int | None = None
    floors_below: int | None = None
    height: float | None = None
    area: float | None = None
    units: int | None = None
    high_rise: bool | None = None
    multi_use: bool | None = None
    special_structure: bool | None = None
    completed: bool | None = None
    special_types: list[str] | None = None


class MasterImage(BaseModel):
    block_id: str
    url: str
    caption: str = ""
    source: str = "file"  # file | external | file_upload


class MasterImageList(BaseModel):
    items: list[MasterImage]


def _multi_select(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": v} for v in values if v]}


def _rich_text(text: str) -> dict[str, Any]:
    return {"rich_text": [{"text": {"content": text}}] if text else []}


def _build_update_props(body: MasterProjectUpdate) -> dict[str, Any]:
    """MasterProjectUpdate → 노션 properties payload (제공된 필드만)."""
    data = body.model_dump(exclude_unset=True)
    props: dict[str, Any] = {}
    if "name" in data:
        props["용역명"] = {"title": [{"text": {"content": data["name"] or ""}}]}
    if "code" in data:
        props["MASTER_CODE"] = _rich_text(data["code"] or "")
    if "address" in data:
        props["주소"] = _rich_text(data["address"] or "")
    if "usage" in data:
        props["용도"] = _multi_select(data["usage"] or [])
    if "structure" in data:
        props["구조형식"] = _multi_select(data["structure"] or [])
    if "special_types" in data:
        props["특수유형"] = _multi_select(data["special_types"] or [])
    if "floors_above" in data:
        props["지상층수"] = {"number": data["floors_above"]}
    if "floors_below" in data:
        props["지하층수"] = {"number": data["floors_below"]}
    if "units" in data:
        props["동수"] = {"number": data["units"]}
    if "height" in data:
        props["높이"] = {"number": data["height"]}
    if "area" in data:
        props["연면적"] = {"number": data["area"]}
    if "high_rise" in data:
        props["고층건축물"] = {"checkbox": bool(data["high_rise"])}
    if "multi_use" in data:
        props["다중이용시설"] = {"checkbox": bool(data["multi_use"])}
    if "special_structure" in data:
        props["특수구조"] = {"checkbox": bool(data["special_structure"])}
    if "completed" in data:
        props["완료"] = {"checkbox": bool(data["completed"])}
    return props


def _block_caption_text(block: dict[str, Any]) -> str:
    arr = (block.get("image") or {}).get("caption") or []
    return "".join(seg.get("plain_text", "") for seg in arr)


def _image_url(image: dict[str, Any]) -> str | None:
    src_type = image.get("type")
    if src_type and (image.get(src_type) or {}).get("url"):
        return image[src_type]["url"]
    return None


def _from_page(page: dict) -> MasterProject:
    props = page.get("properties", {})
    n_above = P.number(props, "지상층수")
    n_below = P.number(props, "지하층수")
    n_units = P.number(props, "동수")
    return MasterProject(
        id=page.get("id", ""),
        name=P.title(props, "용역명"),
        code=P.rich_text(props, "MASTER_CODE"),
        address=P.rich_text(props, "주소"),
        usage=P.multi_select_names(props, "용도"),
        structure=P.multi_select_names(props, "구조형식"),
        floors_above=int(n_above) if n_above is not None else None,
        floors_below=int(n_below) if n_below is not None else None,
        height=P.number(props, "높이"),
        area=P.number(props, "연면적"),
        units=int(n_units) if n_units is not None else None,
        high_rise=P.checkbox(props, "고층건축물"),
        multi_use=P.checkbox(props, "다중이용시설"),
        special_structure=P.checkbox(props, "특수구조"),
        completed=P.checkbox(props, "완료"),
        special_types=P.multi_select_names(props, "특수유형"),
        sub_project_ids=P.relation_ids(props, "Sub-Project"),
        url=page.get("url"),
    )


def _master_from_mirror(row: M.MirrorMaster) -> MasterProject:
    page = {
        "id": row.page_id,
        "properties": row.properties or {},
        "url": row.url or None,
    }
    return _from_page(page)


def _resolve_sub_projects(db: Session, mp: MasterProject) -> None:
    """sub_project_ids → mirror_projects 단일 쿼리 (N+1 제거)."""
    if not mp.sub_project_ids:
        return
    rows = db.execute(
        select(
            M.MirrorProject.page_id,
            M.MirrorProject.code,
            M.MirrorProject.name,
            M.MirrorProject.stage,
        ).where(M.MirrorProject.page_id.in_(mp.sub_project_ids))
    ).all()
    by_id = {pid: (code, name, stage) for pid, code, name, stage in rows}
    for sub_id in mp.sub_project_ids:
        info = by_id.get(sub_id)
        if info:
            code, name, stage = info
            mp.sub_projects.append(
                SubProjectRef(id=sub_id, code=code, name=name, stage=stage)
            )
        else:
            mp.sub_projects.append(SubProjectRef(id=sub_id, name="(미동기화)"))


@router.get("/{page_id}", response_model=MasterProject)
async def get_master_project(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> MasterProject:
    row = db.get(M.MirrorMaster, page_id)
    if row is not None and not row.archived:
        mp = _master_from_mirror(row)
    else:
        # mirror miss → 노션 fallback + upsert
        try:
            page = await notion.get_page(page_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        get_sync().upsert_page("master", page)
        mp = _from_page(page)
    _resolve_sub_projects(db, mp)
    return mp


@router.patch("/{page_id}", response_model=MasterProject)
async def update_master_project(
    page_id: str,
    body: MasterProjectUpdate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> MasterProject:
    props = _build_update_props(body)
    if not props:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다")
    try:
        page = await notion.update_page(page_id, props)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().upsert_page("master", page)
    mp = _from_page(page)
    _resolve_sub_projects(db, mp)
    return mp


# ── 이미지 (페이지 본문 children, mirror_blocks 우선) ──


@router.get("/{page_id}/images", response_model=MasterImageList)
async def list_master_images(
    page_id: str,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    notion: NotionService = Depends(get_notion),
) -> MasterImageList:
    rows = (
        db.execute(
            select(M.MirrorBlock)
            .where(
                M.MirrorBlock.parent_page_id == page_id,
                M.MirrorBlock.type == "image",
            )
            .order_by(M.MirrorBlock.position.asc())
        )
        .scalars()
        .all()
    )
    if not rows:
        # mirror에 없으면 즉시 sync (최초 진입 등)
        try:
            await get_sync().sync_master_blocks(page_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        rows = (
            db.execute(
                select(M.MirrorBlock)
                .where(
                    M.MirrorBlock.parent_page_id == page_id,
                    M.MirrorBlock.type == "image",
                )
                .order_by(M.MirrorBlock.position.asc())
            )
            .scalars()
            .all()
        )
    items: list[MasterImage] = []
    for r in rows:
        image = r.content or {}
        url = _image_url(image)
        if not url:
            continue
        caption_arr = (image.get("caption") or [])
        caption = "".join(seg.get("plain_text", "") for seg in caption_arr)
        items.append(
            MasterImage(
                block_id=r.block_id,
                url=url,
                caption=caption,
                source=image.get("type", "file"),
            )
        )
    return MasterImageList(items=items)


@router.post("/{page_id}/images", response_model=MasterImage)
async def upload_master_image(
    page_id: str,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> MasterImage:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in _IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 이미지 형식: {content_type}",
        )
    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 20MB를 초과합니다")
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일")

    upload_id = await notion.upload_file(
        filename=file.filename or "image",
        content_type=content_type,
        data=data,
    )
    image_block: dict[str, Any] = {
        "object": "block",
        "type": "image",
        "image": {
            "type": "file_upload",
            "file_upload": {"id": upload_id},
        },
    }
    if caption:
        image_block["image"]["caption"] = [
            {"type": "text", "text": {"content": caption[:200]}}
        ]
    try:
        result = await notion.append_block_children(page_id, [image_block])
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    blocks = result.get("results") or []
    if not blocks:
        raise HTTPException(status_code=500, detail="블록 append 응답 비어있음")
    blk = blocks[0]
    image = blk.get("image") or {}
    url = _image_url(image) or ""
    # write-through: mirror_blocks에도 즉시 추가 (page 끝에 append되므로 위치는 sync 시 정렬)
    # 정확한 position이 필요하면 sync_master_blocks 호출
    try:
        await get_sync().sync_master_blocks(page_id)
    except Exception:  # noqa: BLE001
        pass
    return MasterImage(
        block_id=blk.get("id", ""),
        url=url,
        caption=caption,
        source=image.get("type", "file_upload"),
    )


@router.delete("/{page_id}/images/{block_id}", status_code=204)
async def delete_master_image(
    page_id: str,
    block_id: str,
    _user: User = Depends(get_current_user),
    notion: NotionService = Depends(get_notion),
) -> None:
    try:
        await notion.delete_block(block_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    get_sync().delete_block(block_id)
