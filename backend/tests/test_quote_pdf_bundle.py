"""통합 견적 PDF 병합 회귀 테스트."""
from __future__ import annotations

import io
from types import TracebackType
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


def test_quote_bundle_passes_display_date_to_cover_and_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """통합 견적 PDF의 갑지와 자식 견적 모두 같은 헤더 날짜를 사용한다."""
    captured: list[tuple[str, object]] = []

    def fake_cover_pdf(*_args: object, **kwargs: object) -> bytes:
        captured.append(("cover", kwargs.get("display_date")))
        return _blank_pdf_bytes()

    def fake_quote_pdf(*_args: object, **kwargs: object) -> bytes:
        captured.append(("child", kwargs.get("display_date")))
        return _blank_pdf_bytes()

    monkeypatch.setattr(quote_pdf, "build_bundle_cover_pdf", fake_cover_pdf)
    monkeypatch.setattr(quote_pdf, "build_quote_pdf", fake_quote_pdf)

    pdf_bytes = quote_pdf.build_quote_bundle_pdf(
        [
            {
                "form_data": {
                    "input": {"quote_type": "구조설계"},
                    "result": {"final": 1000},
                },
                "doc_number": "26-01-001A",
            }
        ],
        display_date="2026. 05. 25",
    )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 2
    assert captured == [("cover", "2026. 05. 25"), ("child", "2026. 05. 25")]


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


@pytest.mark.asyncio
async def test_download_external_pdf_bytes_sends_drive_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WORKS Storage URL 실제 다운로드에도 Bearer 인증 헤더를 전달한다."""

    captured_headers: list[dict[str, str] | None] = []

    async def fake_get_download_url(
        file_id: str, *, settings: Settings
    ) -> str:
        assert file_id == "file-1"
        return "https://storage.example.test/file.pdf"

    async def fake_get_download_headers(
        *, settings: Settings
    ) -> dict[str, str]:
        return {"Authorization": "Bearer token-1"}

    class FakeResponse:
        content = b"%PDF-1.7\n"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, *, timeout: float, follow_redirects: bool) -> None:
            assert timeout == 60.0
            assert follow_redirects is True

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            headers: dict[str, str] | None = None,
        ) -> FakeResponse:
            assert url == "https://storage.example.test/file.pdf"
            captured_headers.append(headers)
            return FakeResponse()

    monkeypatch.setattr(
        sales_pdf.sso_drive,
        "get_download_url",
        fake_get_download_url,
    )
    monkeypatch.setattr(
        sales_pdf.sso_drive,
        "get_download_headers",
        fake_get_download_headers,
    )
    monkeypatch.setattr(sales_pdf.httpx, "AsyncClient", FakeClient)

    pdf_bytes = await sales_pdf._download_external_pdf_bytes(
        file_id="file-1",
        display_name="외부.pdf",
        settings_=cast(Settings, object()),
    )

    assert pdf_bytes == b"%PDF-1.7\n"
    assert captured_headers == [{"Authorization": "Bearer token-1"}]
