"""Deterministic PDF text normalization and repeated margin detection."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from math import ceil

_ZERO_WIDTH = re.compile("[\u200b-\u200f\u2060\ufeff]")
_CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHENATED_LINE = re.compile(r"(?<=\w)-\s*\n\s*(?=\w)")
_WHITESPACE = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class PageTextBlock:
    text: str
    y0_ratio: float
    y1_ratio: float


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    normalized_text: str
    semantic_body: str
    normalized_text_sha256: str
    semantic_body_sha256: str
    metadata_sha256: str
    header_footer_blocks: tuple[tuple[int, str], ...]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.replace("\u00ad", ""))
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = _CONTROL.sub("", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _HYPHENATED_LINE.sub("", normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def normalize_document(
    pages: list[list[PageTextBlock]], *, metadata: Mapping[str, object]
) -> NormalizedDocument:
    normalized_pages: list[list[tuple[PageTextBlock, str]]] = [
        [(block, normalize_text(block.text)) for block in page if normalize_text(block.text)]
        for page in pages
    ]
    margin_counts: Counter[str] = Counter()
    for page in normalized_pages:
        seen_on_page = {
            _margin_fingerprint(text)
            for block, text in page
            if block.y1_ratio <= 0.1 or block.y0_ratio >= 0.9
        }
        margin_counts.update(seen_on_page)
    minimum_occurrences = max(3, ceil(len(pages) * 0.6))
    repeated = {
        fingerprint for fingerprint, count in margin_counts.items() if count >= minimum_occurrences
    }
    all_text: list[str] = []
    semantic_text: list[str] = []
    excluded: list[tuple[int, str]] = []
    for page_number, page in enumerate(normalized_pages, start=1):
        for block, text in page:
            all_text.append(text)
            in_margin = block.y1_ratio <= 0.1 or block.y0_ratio >= 0.9
            if in_margin and _margin_fingerprint(text) in repeated:
                excluded.append((page_number, text))
            else:
                semantic_text.append(text)
    normalized_text = "\n".join(all_text)
    semantic_body = "\n".join(semantic_text)
    metadata_bytes = json.dumps(
        dict(metadata), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return NormalizedDocument(
        normalized_text=normalized_text,
        semantic_body=semantic_body,
        normalized_text_sha256=_hash_text(normalized_text),
        semantic_body_sha256=_hash_text(semantic_body),
        metadata_sha256=sha256(metadata_bytes).hexdigest(),
        header_footer_blocks=tuple(excluded),
    )


def _margin_fingerprint(value: str) -> str:
    return _DIGITS.sub("#", value).casefold()


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
