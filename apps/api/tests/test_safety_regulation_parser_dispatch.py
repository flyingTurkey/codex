from typing import Any

import pytest
from srbg_api.safety_regulations.dispatch import SafetyRegulationDocumentParser


class RecordingParser:
    def __init__(self, result: str) -> None:
        self.result = result
        self.calls: list[tuple[bytes, dict[str, str]]] = []

    def parse(self, content: bytes, **kwargs: str) -> Any:
        self.calls.append((content, kwargs))
        return self.result


def test_dispatches_pdf_magic_to_pdf_parser() -> None:
    html = RecordingParser("html")
    pdf = RecordingParser("pdf")
    parser = SafetyRegulationDocumentParser(html_parser=html, pdf_parser=pdf)

    result = parser.parse(
        b"%PDF-1.7\nfixture",
        document_version_id="v1",
        canonical_url="https://example.test/rule.pdf",
    )

    assert result == "pdf"
    assert len(pdf.calls) == 1
    assert html.calls == []


def test_dispatches_html_and_rejects_unknown_binary() -> None:
    html = RecordingParser("html")
    pdf = RecordingParser("pdf")
    parser = SafetyRegulationDocumentParser(html_parser=html, pdf_parser=pdf)

    assert (
        parser.parse(
            b"<!doctype html><title>fixture</title>",
            document_version_id="v1",
            canonical_url="https://example.test/rule.html",
        )
        == "html"
    )
    with pytest.raises(ValueError, match="UNSUPPORTED_DOCUMENT_BYTES"):
        parser.parse(
            b"MZ\x90\x00",
            document_version_id="v2",
            canonical_url="https://example.test/rule.exe",
        )
