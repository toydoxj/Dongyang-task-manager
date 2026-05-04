"""프로젝트 담당/stage 이력 — 노션 assign_log DB에 기록.

기존 routers/projects.py 의 _log_assign_change 와 동일 schema. 자동 promote/
reconcile 흐름(서비스)에서도 같은 이력 라인을 쓰기 위해 공통 helper로 분리.
"""
from __future__ import annotations

import logging

from app.services.notion import NotionService
from app.settings import get_settings

logger = logging.getLogger("project.log")


async def log_assign_change(
    notion: NotionService,
    *,
    project_id: str,
    project_name: str,
    actor: str,
    target: str,
    action: str,
) -> None:
    db_id = get_settings().notion_db_assign_log
    if not db_id:
        return
    title = f"{action} · {target} · {project_name}"[:200]
    props = {
        "이벤트": {"title": [{"text": {"content": title}}]},
        "프로젝트": {"relation": [{"id": project_id}]},
        "작업": {"select": {"name": action}},
        "대상 담당자": {"rich_text": [{"text": {"content": target}}]},
        "변경자": {"rich_text": [{"text": {"content": actor}}]},
    }
    try:
        await notion.create_page(db_id, props)
    except Exception:  # noqa: BLE001
        logger.exception("project log 기록 실패 project=%s", project_id)
