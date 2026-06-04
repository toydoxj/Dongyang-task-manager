"""통합 견적 PDF 병합 회귀 테스트."""
from __future__ import annotations

import io
from typing import cast

import pytest
from pypdf import PdfReader, PdfWriter

from app.routers.sales import pdf as sales_pdf
from app.services import quote_pdf
from app.settings import Settings


def _blank_pdf_bytes(page_count: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_quote_bundle_includes_external_attached_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """외부 견적 첨부 PDF는 갑지 뒤에 실제 페이지로 병합되어야 한다."""

    def fake_cover_pdf(*_args: object, **_kwargs: object) -> bytes:
        return _blank_pdf_bytes()

    monkeypatch.setattr(quote_pdf, "build_bundle_cover_pdf", fake_cover_pdf)

    pdf_bytes = quote_pdf.build_quote_bundle_pdf(
        [
            {
                "form_data": {"input": {}, "result": {"final": 1000}},
                "is_external": True,
                "service": "외부 구조검토",
                "attached_pdf_name": "외부.pdf",
                "attached_pdf_bytes": _blank_pdf_bytes(page_count=2),
            }
        ]
    )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 3


@pytest.mark.asyncio
async def test_attach_external_pdf_bytes_downloads_attached_external_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """외부 견적 중 Drive file_id가 있는 항목만 다운로드 bytes를 붙인다."""

    captured: list[tuple[str, str]] = []

    async def fake_download_external_pdf_bytes(
        *,
        file_id: str,
        display_name: str,
        settings_: Settings,
    ) -> bytes:
        captured.append((file_id, display_name))
        return _blank_pdf_bytes()

    monkeypatch.setattr(
        sales_pdf,
        "_download_external_pdf_bytes",
        fake_download_external_pdf_bytes,
    )

    sections: list[dict[str, object]] = [
        {
            "is_external": True,
            "attached_pdf_file_id": "file-1",
            "attached_pdf_name": "외부.pdf",
        },
        {
            "is_external": False,
            "attached_pdf_file_id": "file-2",
        },
        {
            "is_external": True,
            "attached_pdf_file_id": "",
        },
    ]

    enriched = await sales_pdf._attach_external_pdf_bytes(
        sections,
        settings_=cast(Settings, object()),
    )

    assert captured == [("file-1", "외부.pdf")]
    assert isinstance(enriched[0].get("attached_pdf_bytes"), bytes)
    assert "attached_pdf_bytes" not in enriched[1]
    assert "attached_pdf_bytes" not in enriched[2]
