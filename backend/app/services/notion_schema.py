"""노션 schema 자동 보강 — backend가 사용하는 컬럼이 노션 DB에 없으면 부팅 시 생성.

원칙:
- 우리 코드가 의존하는 *최소 컬럼*만 정의. 사용자가 노션에서 추가/수정한 옵션은 존중.
- 누락된 property만 PATCH (이미 있는 건 건드리지 않음).
- 실패해도 부팅은 계속 (warn 로그만).
"""
from __future__ import annotations

import logging
from typing import Any

from app.exceptions import NotionApiError
from app.services.notion import NotionService
from app.settings import Settings

logger = logging.getLogger("notion.schema")


def _select(options: list[tuple[str, str]]) -> dict[str, Any]:
    """select property 정의 헬퍼. options=[(name, color), ...]."""
    return {
        "select": {
            "options": [{"name": n, "color": c} for n, c in options]
        }
    }


# ── DB별 최소 schema ──

# 업무 TASK DB — 코드에서 참조하는 한국어 컬럼 (이미 노션에 있는 컬럼은 여기 정의 X)
TASK_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "난이도": _select(
        [
            ("매우높음", "red"),
            ("높음", "orange"),
            ("중간", "yellow"),
            ("낮음", "blue"),
            ("매우낮음", "gray"),
        ]
    ),
    "분류": _select(
        [
            ("프로젝트", "blue"),
            ("개인업무", "gray"),
            ("사내잡무", "brown"),
            ("교육", "green"),
            ("서비스", "purple"),
            ("외근", "orange"),
            ("출장", "red"),
            ("휴가", "pink"),
        ]
    ),
    # 활동 유형 — 분류와 독립. 프로젝트 task가 외근/출장일 수 있음.
    "활동": _select(
        [
            ("사무실", "default"),
            ("외근", "orange"),
            ("출장", "red"),
        ]
    ),
}

# 메인 프로젝트 DB — WORKS Drive 폴더 URL (Phase 2)
PROJECT_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "WORKS Drive URL": {"url": {}},
}
MASTER_DB_REQUIRED: dict[str, dict[str, Any]] = {}
CLIENT_DB_REQUIRED: dict[str, dict[str, Any]] = {}

# 날인요청 DB
# 신 옵션(1차검토 중 / 2차검토 중 / 승인)을 운영 표준으로 채택하되, 노션은 select option을
# 자동 제거하지 않으므로 옛 옵션(요청/팀장승인/관리자승인/완료/도면/검토서)이 그대로
# 남아 기존 row를 깨뜨리지 않음. read 시 seal_logic.normalize_*가 신 옵션으로 매핑.
SEAL_REQUEST_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "날인유형": _select(
        [
            ("구조계산서", "blue"),
            ("구조안전확인서", "green"),
            ("구조검토서", "purple"),
            ("구조도면", "orange"),
            ("보고서", "pink"),
            ("기타", "gray"),
        ]
    ),
    "상태": _select(
        [
            ("1차검토 중", "yellow"),
            ("2차검토 중", "blue"),
            ("승인", "green"),
            ("반려", "red"),
            # 구조검토서의 중간 문서번호를 취소했을 때 — 흔적 row를 잠그기 위한
            # 전용 sentinel. PATCH/attachments는 이 상태에서 거부됨.
            ("취소", "gray"),
        ]
    ),
    "요청자": {"rich_text": {}},
    "팀장처리자": {"rich_text": {}},
    "관리자처리자": {"rich_text": {}},
    "요청일": {"date": {}},
    "팀장처리일": {"date": {}},
    "관리자처리일": {"date": {}},
    "제출예정일": {"date": {}},
    "비고": {"rich_text": {}},
    "첨부파일": {"files": {}},  # 호환용 — Drive 전환 후 비어있을 수 있음
    "첨부메타": {"rich_text": {}},  # S3 + Works Drive attachments JSON
    # ── docs/request.md 추가 컬럼 ──
    "실제출처": {"rich_text": {}},
    "용도": {"rich_text": {}},
    "Revision": {"number": {}},
    "안전확인서포함": {"checkbox": {}},
    "내용요약": {"rich_text": {}},
    "문서번호": {"rich_text": {}},  # 구조검토서: YY-의견-NNN
    "문서종류": {"rich_text": {}},  # 기타 유형 전용
    "첨부폴더URL": {"url": {}},  # Works Drive 일자 폴더 web URL
    "반려사유": {"rich_text": {}},  # 비고와 분리해 read 단순화
    "연결TASK": {"rich_text": {}},  # 자동 생성한 노션 TASK page_id (lifecycle 동기화)
}


# 건의사항 DB
SUGGESTION_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "내용": {"rich_text": {}},
    "작성자": {"rich_text": {}},
    "진행상황": _select(
        [
            ("접수", "gray"),
            ("검토중", "yellow"),
            ("완료", "green"),
            ("반려", "red"),
        ]
    ),
    "조치내용": {"rich_text": {}},
}


async def _ensure_db(
    notion: NotionService,
    db_id: str,
    required: dict[str, dict[str, Any]],
    *,
    label: str,
) -> int:
    """단일 DB의 누락 컬럼 추가. 반환: 추가된 컬럼 수."""
    if not db_id or not required:
        return 0
    try:
        ds = await notion.get_data_source(db_id)
    except NotionApiError as exc:
        logger.warning("schema check %s 실패: %s", label, exc)
        return 0
    existing = ds.get("properties") or {}
    missing = {k: v for k, v in required.items() if k not in existing}
    if not missing:
        return 0
    try:
        await notion.update_data_source_schema(db_id, properties=missing)
        logger.info(
            "노션 schema 자동 추가 [%s]: %s",
            label,
            ", ".join(missing.keys()),
        )
        return len(missing)
    except NotionApiError as exc:
        logger.warning("schema update %s 실패: %s", label, exc)
        return 0


async def ensure_all_schemas(notion: NotionService, settings: Settings) -> None:
    """모든 DB schema 보강. 부팅 시 1회 호출."""
    await _ensure_db(notion, settings.notion_db_tasks, TASK_DB_REQUIRED, label="tasks")
    await _ensure_db(
        notion, settings.notion_db_projects, PROJECT_DB_REQUIRED, label="projects"
    )
    await _ensure_db(
        notion, settings.notion_db_master, MASTER_DB_REQUIRED, label="master"
    )
    await _ensure_db(
        notion, settings.notion_db_clients, CLIENT_DB_REQUIRED, label="clients"
    )
    await _ensure_db(
        notion,
        settings.notion_db_suggestions,
        SUGGESTION_DB_REQUIRED,
        label="suggestions",
    )
    await _ensure_db(
        notion,
        settings.notion_db_seal_requests,
        SEAL_REQUEST_DB_REQUIRED,
        label="seal_requests",
    )
