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

# 프로젝트 계약 항목 DB — relation은 사용자가 노션에서 직접 생성해야 함
# (ensure는 select/number/text/url만 보강 가능; relation은 schema에서 생략)
CONTRACT_ITEM_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "금액": {"number": {}},
    "VAT": {"number": {}},
    "정렬": {"number": {}},
}

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
    # `실제출처`는 노션에 이미 거래처 DB와 연결된 relation 컬럼으로 존재. schema에
    # 명시하지 않고 그대로 사용한다(read는 relation_ids, write는 relation 형식).
    "용도": {"rich_text": {}},
    "Revision": {"number": {}},
    "안전확인서포함": {"checkbox": {}},
    "내용요약": {"rich_text": {}},
    "문서번호": {"rich_text": {}},  # 구조검토서: YY-의견-NNN
    "문서종류": {"rich_text": {}},  # 기타 유형 전용
    "첨부폴더URL": {"url": {}},  # Works Drive 일자 폴더 web URL
    "반려사유": {"rich_text": {}},  # 비고와 분리해 read 단순화
    "연결TASK": {"rich_text": {}},  # 요청자용 자동 TASK page_id (lifecycle 동기화)
    "1차검토TASK": {"rich_text": {}},  # 1차 검토자(팀장)용 자동 TASK page_id
    "2차검토TASK": {"rich_text": {}},  # 2차 검토자(admin)용 자동 TASK page_id
}


# 영업(Sales) DB — 사장이 운영하던 "견적서 작성 리스트" DB를 영업 파이프라인으로
# 확장한 형태. 도메인 컬럼 대부분(견적서명/견적금액/연면적/지상층수/지하층수/동수/
# 업무내용/의뢰처/비고/제출일 등)은 사장이 이미 정의·운영 중이므로 본 자동 보강
# 대상에서 제외한다. 본 dict는 "코드가 추가로 도입한 영업 분류 차원"만 보강한다.
#
# kind는 "수주영업"(견적·입찰)과 "기술지원"(수주 전 자문) 2갈래.
# stage는 두 kind의 옵션을 한 select에 합친다(노션 select는 그룹화 미지원).
# UI에서 kind에 따라 노출 옵션을 필터링하지만 노션 자체는 자유 선택.
# `전환된 프로젝트`(프로젝트 DB relation)는 update_data_source_schema가 relation
# 자동 생성을 지원하지 않으므로 운영자가 노션 UI에서 직접 추가해야 한다.
# `상위 영업건` self relation은 PR-M4b에서 사용 폐기 — 노션 UI에서 운영자가
# 수동 정리 권장 (data 없음 확인 후 삭제).
SALES_DB_REQUIRED: dict[str, dict[str, Any]] = {
    "유형": _select(
        [
            ("수주영업", "blue"),
            ("기술지원", "purple"),
        ]
    ),
    # 단계: 수주영업 5종 (사장 결정 — 보수적 5단계 체계).
    # 사용자가 노션에서 select 옵션 이름을 rename하면 옵션 id가 유지되어
    # 기존 row의 단계 값이 자동으로 새 이름으로 보임 — 데이터 손실 없음.
    # rename 매핑: 견적준비→준비, 입찰대기→진행, 우선협상→제출, 낙찰→완료, 실주→종결.
    # 수주확률은 별도 number 컬럼으로 PM이 직접 입력 (단계 자동 확률 모델 폐기).
    "단계": _select(
        [
            ("준비", "yellow"),
            ("진행", "orange"),
            ("제출", "blue"),
            ("완료", "green"),
            ("종결", "gray"),
        ]
    ),
    "입찰여부": {"checkbox": {}},
    # 수주확률 — PM이 0~100 직접 입력. expected_revenue = 견적금액 × probability/100.
    # 단계별 자동 확률은 폐기됨(사용자 결정 — 단계와 확률을 분리해 유연성 확보).
    "수주확률": {"number": {}},
    # 영업코드 — 자동 부여 ({YY}-영업-{NNN}). 노션에서 수동 수정 허용.
    "영업코드": {"rich_text": {}},
    # 견적서 문서번호 — 견적서 작성 툴(PR5) 자동 부여 ({YY}-{CC}-{NNN}).
    "문서번호": {"rich_text": {}},
    # 영업 위치 — 영업 row 단위. 견적서 탭에서 echo로 자동 채움.
    "위치": {"rich_text": {}},
    # 견적서 첨부 — WORKS Drive에 저장된 PDF의 web url 보관
    "견적서첨부": {"files": {}},
    # 통합 견적서 첨부 (PR-G2) — parent_lead_id로 묶인 자식 견적까지 1 PDF로
    # 합친 통합본의 web url. parent 영업에만 의미. 단일 PDF는 견적서첨부에 그대로 보존.
    "통합견적서첨부": {"files": {}},
    # 견적서 종류 — 11종 + 내진평가 패키지 부속 2종 = 13 옵션
    "견적서종류": _select(
        [
            ("구조설계", "blue"),
            ("구조검토", "purple"),
            ("성능기반내진설계", "pink"),
            ("정기안전점검", "yellow"),
            ("정밀점검", "orange"),
            ("정밀안전진단", "red"),
            ("건축물관리법점검", "brown"),
            ("내진성능평가", "green"),
            # 내진평가 패키지 부속 — 별 영업 row + 통합 PDF (PR-G1) 패턴
            ("내진보강설계", "green"),
            ("3자검토", "green"),
            ("구조감리", "default"),
            ("현장기술지원", "gray"),
            ("기타", "default"),
        ]
    ),
    # 담당자 — 기존 견적서 DB가 multi_select 텍스트로 운영 중이므로 동일 패턴.
    # /me 페이지의 assignee 매칭 로직을 그대로 재사용한다. 옵션은 노션이 사용자
    # 입력 시 자동 등록 (task DB와 동일).
    "담당자": {"multi_select": {}},
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


def _missing_select_options(
    existing_prop: dict[str, Any], required_prop: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """기존 select property에 누락된 옵션이 있으면 union 결과(전체 옵션 list) 반환.

    노션 update_data_source_schema는 select options 부분 patch가 아니라 **전체 list
    교체** 방식. 기존 옵션 + 누락 옵션을 합쳐 다시 보낸다. None이면 보강 불필요.
    """
    if "select" not in required_prop:
        return None
    if existing_prop.get("type") not in (None, "select"):
        return None
    existing_opts = (existing_prop.get("select") or {}).get("options") or []
    required_opts = (required_prop.get("select") or {}).get("options") or []
    existing_names = {o.get("name") for o in existing_opts if o.get("name")}
    missing = [
        o for o in required_opts if o.get("name") and o["name"] not in existing_names
    ]
    if not missing:
        return None
    # 기존 옵션 보존(id 포함) + 누락 옵션 append. id가 없는 옵션은 노션이 새로 발급.
    return list(existing_opts) + missing


async def _ensure_db(
    notion: NotionService,
    db_id: str,
    required: dict[str, dict[str, Any]],
    *,
    label: str,
) -> int:
    """단일 DB의 누락 컬럼 + 누락 select 옵션 보강. 반환: 변경된 property 수.

    - 컬럼 자체 누락 → 새 property 추가
    - select 컬럼 존재하지만 옵션 일부 누락 → 옵션 union으로 patch
    """
    if not db_id or not required:
        return 0
    try:
        ds = await notion.get_data_source(db_id)
    except NotionApiError as exc:
        logger.warning("schema check %s 실패: %s", label, exc)
        return 0
    existing = ds.get("properties") or {}
    patch: dict[str, dict[str, Any]] = {}
    new_columns: list[str] = []
    option_patches: list[str] = []
    for name, spec in required.items():
        if name not in existing:
            patch[name] = spec
            new_columns.append(name)
            continue
        union = _missing_select_options(existing[name], spec)
        if union is not None:
            patch[name] = {"select": {"options": union}}
            option_patches.append(name)
    if not patch:
        return 0
    try:
        await notion.update_data_source_schema(db_id, properties=patch)
        if new_columns:
            logger.info(
                "노션 schema 컬럼 추가 [%s]: %s", label, ", ".join(new_columns)
            )
        if option_patches:
            logger.info(
                "노션 schema 옵션 보강 [%s]: %s",
                label,
                ", ".join(option_patches),
            )
        return len(patch)
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
    await _ensure_db(
        notion,
        settings.notion_db_contract_items,
        CONTRACT_ITEM_DB_REQUIRED,
        label="contract_items",
    )
    await _ensure_db(
        notion,
        settings.notion_db_sales,
        SALES_DB_REQUIRED,
        label="sales",
    )
