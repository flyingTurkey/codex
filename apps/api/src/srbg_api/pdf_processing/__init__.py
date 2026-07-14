"""Bounded PDF/OCR processing owned by the modular ingestion application."""

from srbg_api.pdf_processing.change_detection import classify_version_change
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.pdf_processing.security import inspect_pdf_bytes, inspect_zip_bytes

__all__ = [
    "PdfDocumentParser",
    "classify_version_change",
    "inspect_pdf_bytes",
    "inspect_zip_bytes",
]
