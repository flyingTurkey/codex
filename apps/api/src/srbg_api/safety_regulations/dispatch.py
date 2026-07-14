"""Fail-closed dispatch to the existing HTML or PDF regulation parser."""

from typing import Protocol

from srbg_api.safety_regulations.parser import ParsedSafetyRegulation


class RegulationParser(Protocol):
    def parse(
        self,
        content: bytes,
        *,
        document_version_id: str,
        canonical_url: str,
    ) -> ParsedSafetyRegulation: ...


class SafetyRegulationDocumentParser:
    def __init__(
        self,
        *,
        html_parser: RegulationParser,
        pdf_parser: RegulationParser,
    ) -> None:
        self._html_parser = html_parser
        self._pdf_parser = pdf_parser

    def parse(
        self,
        content: bytes,
        *,
        document_version_id: str,
        canonical_url: str,
    ) -> ParsedSafetyRegulation:
        kwargs = {
            "document_version_id": document_version_id,
            "canonical_url": canonical_url,
        }
        if content.startswith(b"%PDF-"):
            return self._pdf_parser.parse(content, **kwargs)
        prefix = content[:512].lstrip().lower()
        if prefix.startswith((b"<!doctype html", b"<html")):
            return self._html_parser.parse(content, **kwargs)
        raise ValueError("UNSUPPORTED_DOCUMENT_BYTES")
