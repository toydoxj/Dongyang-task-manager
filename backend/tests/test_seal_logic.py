"""seal_logic — 검토구분 정규화 / 제목 템플릿 / 구조검토서 문서번호 발급 검증."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from app.services import seal_logic as SL

# ── normalize_type / normalize_status ──


def test_normalize_type_legacy_to_new() -> None:
    assert SL.normalize_type("도면") == "구조도면"
    assert SL.normalize_type("검토서") == "구조검토서"


def test_normalize_type_new_passthrough() -> None:
    for t in SL.SEAL_TYPES_NEW:
        assert SL.normalize_type(t) == t


def test_normalize_type_unknown_passthrough() -> None:
    assert SL.normalize_type("기타") == "기타"
    assert SL.normalize_type("알수없음") == "알수없음"


def test_normalize_status_legacy_to_new() -> None:
    assert SL.normalize_status("요청") == "1차검토 중"
    assert SL.normalize_status("팀장승인") == "2차검토 중"
    assert SL.normalize_status("관리자승인") == "승인"
    assert SL.normalize_status("완료") == "승인"


def test_normalize_status_new_passthrough() -> None:
    for s in ("1차검토 중", "2차검토 중", "승인", "반려"):
        assert SL.normalize_status(s) == s


# ── build_title — 6종 패턴 ──


def test_build_title_calc() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조계산서",
            fields={"revision": 2, "용도": "허가용"},
        )
        == "구조계산서_rev2_허가용"
    )


def test_build_title_calc_zero_rev() -> None:
    """revision=0/None이면 rev0."""
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조계산서",
            fields={"revision": 0, "용도": "허가용"},
        )
        == "구조계산서_rev0_허가용"
    )


def test_build_title_safety_cert() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조안전확인서",
            fields={"용도": "착공용"},
        )
        == "구조안전확인서_착공용"
    )


def test_build_title_review() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조검토서",
            fields={"문서번호": "26-의견-005"},
        )
        == "26-의견-005_구조검토서"
    )


def test_build_title_drawing() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="구조도면",
            fields={"용도": "실시설계"},
        )
        == "구조도면_실시설계"
    )


def test_build_title_report() -> None:
    assert SL.build_title(code="DY-26-100", seal_type="보고서", fields={}) == (
        "보고서"
    )


def test_build_title_etc() -> None:
    assert (
        SL.build_title(
            code="DY-26-100",
            seal_type="기타",
            fields={"문서종류": "공사관리계획"},
        )
        == "공사관리계획"
    )


def test_build_title_etc_default() -> None:
    """문서종류 비어있으면 '기타'로."""
    assert SL.build_title(code="DY-26-100", seal_type="기타", fields={}) == (
        "기타"
    )


# ── mirror 기반 구조검토서 문서번호 ──


def _mirror_row(doc_no: str):
    return SimpleNamespace(
        properties={
            "문서번호": {
                "rich_text": [{"plain_text": doc_no}],
            }
        }
    )


class _FakeScalars:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class _FakeResult:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.rows)


class _FakeDb:
    def __init__(self, rows: list[Any]):
        self.rows = rows

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return _FakeResult(self.rows)


def test_issue_first_doc_number_from_mirror() -> None:
    yy = date.today().strftime("%y")
    db = _FakeDb([])
    assert SL.issue_review_doc_number_from_mirror(db) == f"{yy}-의견-001"


def test_next_review_doc_number_from_mirror() -> None:
    yy = date.today().strftime("%y")
    db = _FakeDb(
        [
            _mirror_row(f"{yy}-의견-001"),
            _mirror_row(f"{yy}-의견-005"),
            _mirror_row(f"{yy}-의견-003"),
        ]
    )
    assert SL.next_review_doc_number_from_mirror(db) == f"{yy}-의견-006"


def test_issue_skips_other_year_from_mirror() -> None:
    yy = date.today().strftime("%y")
    db = _FakeDb(
        [
            _mirror_row(f"{yy}-의견-001"),
            _mirror_row("99-의견-999"),
        ]
    )
    assert SL.issue_review_doc_number_from_mirror(db) == f"{yy}-의견-002"


def test_is_last_review_doc_number_from_mirror() -> None:
    yy = date.today().strftime("%y")
    db = _FakeDb([_mirror_row(f"{yy}-의견-001"), _mirror_row(f"{yy}-의견-005")])
    assert SL.is_last_review_doc_number_from_mirror(db, doc_no=f"{yy}-의견-005")
    assert not SL.is_last_review_doc_number_from_mirror(db, doc_no=f"{yy}-의견-001")


def test_is_last_empty_doc_no_from_mirror() -> None:
    db = _FakeDb([])
    assert not SL.is_last_review_doc_number_from_mirror(db, doc_no="")
