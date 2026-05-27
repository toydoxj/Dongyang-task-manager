"""회귀 테스트 — mirror-direct write 포맷(plain_text 없음)을 read helper가 읽는지.

PR-FR로 task/project를 노션 호출 없이 mirror에 직접 쓰면서, write 포맷
({"text": {"content": v}})에는 노션 read 응답의 `plain_text`가 없다. 과거
P.title/P.rich_text가 plain_text만 읽어 mirror read 시 제목·비고가 빈 값으로
사라지는 cascade 발생 (사용자 보고: TASK 내용 수정 시 제목 사라짐 / 수정 안 됨).
"""
from __future__ import annotations

from app.models.task import Task, _rich_text, _title
from app.services import notion_props as P


def test_title_reads_write_format() -> None:
    """_title() write 포맷(plain_text 없음)을 P.title이 읽는다."""
    props = {"내용": _title("구조검토 견적")}
    assert "plain_text" not in props["내용"]["title"][0]  # write 포맷 확인
    assert P.title(props, "내용") == "구조검토 견적"


def test_rich_text_reads_write_format() -> None:
    """_rich_text() write 포맷을 P.rich_text가 읽는다 (비고/CODE 등)."""
    props = {"비고": _rich_text("현장 방문 후 재산정")}
    assert P.rich_text(props, "비고") == "현장 방문 후 재산정"


def test_rich_text_multi_segment_write_format() -> None:
    """여러 segment write 포맷 concat."""
    props = {
        "비고": {
            "rich_text": [
                {"text": {"content": "앞"}},
                {"text": {"content": "뒤"}},
            ]
        }
    }
    assert P.rich_text(props, "비고") == "앞뒤"


def test_title_reads_notion_read_format() -> None:
    """노션 API read 응답(plain_text 포함)도 그대로 읽는다 (회귀 방지)."""
    props = {"내용": {"title": [{"plain_text": "x", "text": {"content": "x"}}]}}
    assert P.title(props, "내용") == "x"


def test_empty_title_stays_empty() -> None:
    """빈 title/rich_text는 빈 문자열 — 기존 동작 보존."""
    assert P.title({"내용": _title("")}, "내용") == ""
    assert P.rich_text({"비고": _rich_text("")}, "비고") == ""
    assert P.title({}, "내용") == ""


def test_task_from_notion_page_preserves_write_format() -> None:
    """update_task가 mirror에 쓰는 merged_props(write 포맷)로 Task 왕복 시 보존.

    cascade 핵심 재현: props["내용"]=_title(v) → from_notion_page → title==v.
    수정 전엔 ''(빈 제목)이 되어 사라졌다.
    """
    page = {
        "id": "t1",
        "properties": {
            "내용": _title("내력검토 용역"),
            "비고": _rich_text("현장 메모"),
        },
    }
    task = Task.from_notion_page(page)
    assert task.title == "내력검토 용역"
    assert task.note == "현장 메모"


# ── normalize_properties_for_mirror (mirror 저장 직전 정규화) ──

norm = P.normalize_properties_for_mirror


def test_normalize_adds_plain_text_to_write_title() -> None:
    out = norm({"내용": {"title": [{"text": {"content": "제목"}}]}})
    assert out["내용"]["title"][0]["plain_text"] == "제목"


def test_normalize_adds_plain_text_to_write_rich_text() -> None:
    out = norm({"비고": {"rich_text": [{"text": {"content": "메모"}}]}})
    assert out["비고"]["rich_text"][0]["plain_text"] == "메모"


def test_normalize_idempotent_on_read_format() -> None:
    """이미 plain_text 있으면 원본 그대로 반환 (변경 없음)."""
    props = {"내용": {"title": [{"plain_text": "x", "text": {"content": "x"}}]}}
    assert norm(props) is props


def test_normalize_does_not_mutate_original() -> None:
    props = {"내용": {"title": [{"text": {"content": "제목"}}]}}
    out = norm(props)
    assert out is not props
    assert "plain_text" not in props["내용"]["title"][0]  # 원본 불변


def test_normalize_skips_mention_without_text() -> None:
    """text 키 없는 segment(mention/equation)는 보강하지 않음."""
    props = {"내용": {"title": [{"mention": {"user": {}}}]}}
    out = norm(props)
    assert "plain_text" not in out["내용"]["title"][0]


def test_normalize_ignores_non_text_properties() -> None:
    """title/rich_text 아닌 property(date/people/rollup)는 손대지 않음."""
    props = {
        "기간": {"date": {"start": "2026-05-22"}},
        "담당자": {"people": [{"id": "u1"}]},
        "Master Code": {"rollup": {"type": "array", "array": []}},
    }
    assert norm(props) is props


def test_normalize_empty() -> None:
    assert norm({}) == {}
    assert norm(None) is None


def test_normalize_mixed() -> None:
    props = {
        "내용": {"title": [{"text": {"content": "T"}}]},
        "비고": {"rich_text": [{"plain_text": "R", "text": {"content": "R"}}]},
        "기간": {"date": {"start": "2026-05-22"}},
    }
    out = norm(props)
    assert out["내용"]["title"][0]["plain_text"] == "T"   # write → 보강
    assert out["비고"]["rich_text"][0]["plain_text"] == "R"  # read → 유지
    assert out["기간"] == props["기간"]                    # date 그대로
