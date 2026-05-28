"""날인요청 비즈니스 로직 — 검토구분 매핑, 제목 템플릿, 구조검토서 문서번호 발급.

router(seal_requests.py)에서 호출하며, NotionService 외 외부 의존 없이 순수 도메인
로직만 담는다. 단위 테스트가 쉽게 작성되도록 의도.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import mirror as M
from app.services import notion_props as P

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


def _lock_review_doc_sequence(db: Session, year_yy: str) -> None:
    """구조검토서 문서번호 발급용 transaction advisory lock.

    운영 DB는 PostgreSQL. 테스트/로컬 등 다른 dialect에서는 lock 없이 계산한다.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"seal-review-doc:{year_yy}"},
    )


def list_review_doc_numbers_from_mirror(
    db: Session, *, year_yy: str
) -> list[int]:
    """mirror_seal_requests에서 당해년도 구조검토서 NNN 목록 조회."""
    rows = db.execute(
        select(M.MirrorSealRequest).where(
            M.MirrorSealRequest.archived.is_(False),
            M.MirrorSealRequest.seal_type == "구조검토서",
        )
    ).scalars().all()
    out: list[int] = []
    for row in rows:
        no = P.rich_text(row.properties or {}, "문서번호").strip()
        n = _parse_review_n(no, year_yy)
        if n is not None:
            out.append(n)
    return out


def next_review_doc_number_from_mirror(
    db: Session, *, lock: bool = False
) -> str:
    """{YY}-의견-{NNN} 다음 번호 계산. preview는 lock 없이, 실제 발급은 lock 사용."""
    yy = date.today().strftime("%y")
    if lock:
        _lock_review_doc_sequence(db, yy)
    used = list_review_doc_numbers_from_mirror(db, year_yy=yy)
    n = (max(used) + 1) if used else 1
    return f"{yy}-의견-{n:03d}"


def issue_review_doc_number_from_mirror(db: Session) -> str:
    """구조검토서 문서번호 실제 발급용. transaction advisory lock으로 동시 발급을 줄인다."""
    return next_review_doc_number_from_mirror(db, lock=True)


def is_last_review_doc_number_from_mirror(db: Session, *, doc_no: str) -> bool:
    """주어진 구조검토서 번호가 mirror 기준 마지막 번호인지 확인."""
    if not doc_no:
        return False
    yy = doc_no.split("-")[0] if "-" in doc_no else date.today().strftime("%y")
    target = _parse_review_n(doc_no, yy)
    if target is None:
        return False
    _lock_review_doc_sequence(db, yy)
    used = list_review_doc_numbers_from_mirror(db, year_yy=yy)
    return not any(n > target for n in used if n != target)
