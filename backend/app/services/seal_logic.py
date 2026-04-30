"""날인요청 비즈니스 로직 — 검토구분 매핑, 제목 템플릿, 구조검토서 문서번호 발급.

router(seal_requests.py)에서 호출하며, NotionService 외 외부 의존 없이 순수 도메인
로직만 담는다. 단위 테스트가 쉽게 작성되도록 의도.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.services import notion_props as P
from app.services.notion import NotionService

# 신 옵션 — docs/request.md
SEAL_TYPES_NEW: tuple[str, ...] = (
    "구조계산서",
    "구조안전확인서",
    "구조검토서",
    "구조도면",
    "보고서",
    "기타",
)

# 옛 옵션 → 신 옵션 (read 단방향 매핑). schema에서 옛 옵션을 자동 제거할 수 없으므로
# 기존 row의 select 값을 호환 처리한다.
LEGACY_TYPE_MAP: dict[str, str] = {
    "도면": "구조도면",
    "검토서": "구조검토서",
}

LEGACY_STATUS_MAP: dict[str, str] = {
    "요청": "1차검토 중",
    "팀장승인": "2차검토 중",
    "관리자승인": "승인",
    "완료": "승인",
}

VALID_TYPES: set[str] = set(SEAL_TYPES_NEW) | set(LEGACY_TYPE_MAP)
VALID_STATUSES: set[str] = {
    "1차검토 중",
    "2차검토 중",
    "승인",
    "반려",
    "취소",
} | set(LEGACY_STATUS_MAP)


def normalize_type(t: str) -> str:
    """옛 옵션을 신 옵션으로 매핑. 신 옵션은 그대로."""
    return LEGACY_TYPE_MAP.get(t, t)


def normalize_status(s: str) -> str:
    return LEGACY_STATUS_MAP.get(s, s)


# ── 제목 자동 생성 ──


def build_title(*, code: str, seal_type: str, fields: dict[str, Any]) -> str:
    """검토구분별 제목 템플릿. fields는 검토구분에 따라 다른 키를 사용.

    | seal_type        | fields keys              | template                          |
    |------------------|--------------------------|-----------------------------------|
    | 구조계산서       | revision, 용도           | {code}_구조계산서_rev{N}_{용도}   |
    | 구조안전확인서   | 용도                     | {code}_구조안전확인서_{용도}      |
    | 구조검토서       | 문서번호                 | {code}_{문서번호}_구조검토서      |
    | 구조도면         | 용도                     | {code}_구조도면_{용도}            |
    | 보고서           | (없음)                   | {code}_보고서                     |
    | 기타             | 문서종류                 | {code}_{문서종류}                 |

    값이 비어있으면 placeholder를 채워 일단 문자열 반환 (router에서 검증).
    """
    c = (code or "").strip() or "?"
    if seal_type == "구조계산서":
        rev = fields.get("revision")
        purpose = (fields.get("용도") or "").strip() or "?"
        rev_str = str(int(rev)) if isinstance(rev, int | float) and rev else "0"
        return f"{c}_구조계산서_rev{rev_str}_{purpose}"
    if seal_type == "구조안전확인서":
        purpose = (fields.get("용도") or "").strip() or "?"
        return f"{c}_구조안전확인서_{purpose}"
    if seal_type == "구조검토서":
        doc_no = (fields.get("문서번호") or "").strip() or "?"
        return f"{c}_{doc_no}_구조검토서"
    if seal_type == "구조도면":
        purpose = (fields.get("용도") or "").strip() or "?"
        return f"{c}_구조도면_{purpose}"
    if seal_type == "보고서":
        return f"{c}_보고서"
    if seal_type == "기타":
        kind = (fields.get("문서종류") or "").strip() or "기타"
        return f"{c}_{kind}"
    # fallback (legacy 호출 등)
    return f"{c}_{seal_type}"


# ── 구조검토서 문서번호 ──


def _parse_review_n(doc_no: str, yy: str) -> int | None:
    """'YY-의견-NNN'에서 NNN(int) 추출. prefix가 다르면 None."""
    prefix = f"{yy}-의견-"
    if not doc_no.startswith(prefix):
        return None
    tail = doc_no[len(prefix) :]
    try:
        return int(tail)
    except ValueError:
        return None


async def list_review_doc_numbers(
    notion: NotionService, db_id: str, *, year_yy: str
) -> list[int]:
    """당해년도(YY) 발급된 구조검토서 NNN 목록 — archive된 row는 제외(노션 default)."""
    pages = await notion.query_all(
        db_id,
        filter={
            "and": [
                {"property": "날인유형", "select": {"equals": "구조검토서"}},
                {"property": "문서번호", "rich_text": {"starts_with": f"{year_yy}-"}},
            ]
        },
    )
    out: list[int] = []
    for p in pages:
        no = P.rich_text(p.get("properties", {}), "문서번호").strip()
        n = _parse_review_n(no, year_yy)
        if n is not None:
            out.append(n)
    return out


async def issue_review_doc_number(notion: NotionService, db_id: str) -> str:
    """{YY}-의견-{NNN} 발급. NNN = 당해년도 max(NNN) + 1.

    - archive된 row의 번호는 자동 회수 (노션 query default가 archive 제외)
    - race: 두 사용자가 동시에 호출하면 같은 번호 발급 위험. router에서 발급 후
      `assert_unique_doc_number()` 재확인 + 1회 재시도로 best-effort 처리.
    """
    yy = date.today().strftime("%y")
    used = await list_review_doc_numbers(notion, db_id, year_yy=yy)
    n = (max(used) + 1) if used else 1
    return f"{yy}-의견-{n:03d}"


async def is_last_review_doc_number(
    notion: NotionService, db_id: str, *, doc_no: str
) -> bool:
    """주어진 문서번호가 당해년도 마지막 번호인지 (이후 번호가 발급된 적 없는지).

    True → 취소 시 hard archive 가능 (다음 발급에서 재사용).
    False → [날인취소] prefix로 흔적 남김.
    """
    if not doc_no:
        return False
    yy = doc_no.split("-")[0] if "-" in doc_no else date.today().strftime("%y")
    target = _parse_review_n(doc_no, yy)
    if target is None:
        return False
    used = await list_review_doc_numbers(notion, db_id, year_yy=yy)
    # 자기 자신 제외하고 더 큰 번호가 있는지
    return not any(n > target for n in used if n != target)
