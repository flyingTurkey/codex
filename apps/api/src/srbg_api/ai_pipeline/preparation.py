"""Deterministic, bounded server-side assembly of untrusted document blocks."""

import re
from dataclasses import dataclass
from hashlib import sha256

from srbg_api.ai_pipeline.contracts import EvidenceAnchor
from srbg_api.ai_pipeline.pipeline import PipelineInputRejected


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    block_id: str
    page_number: int
    text: str
    locator_value: str
    repeated_header_footer: bool = False


@dataclass(frozen=True, slots=True)
class PreparedDocumentInput:
    text: str
    input_sha256: str
    anchors: dict[str, EvidenceAnchor]
    block_ids: tuple[str, ...]


def prepare_document_input(
    *,
    document_version_id: str,
    title: str,
    source_name: str,
    blocks: list[DocumentBlock],
    max_characters: int,
) -> PreparedDocumentInput:
    if max_characters <= 0:
        raise ValueError("max_characters must be positive")
    prefix = f"标题: {_normalize(title)}\n来源: {_normalize(source_name)}"
    selected: list[tuple[DocumentBlock, str]] = []
    used = len(prefix)
    for block in sorted(blocks, key=lambda item: (item.page_number, item.block_id)):
        normalized = _normalize(block.text)
        if not normalized or block.repeated_header_footer:
            continue
        rendered = f"\n[页 {block.page_number} 块 {block.block_id}]\n{normalized}"
        if used + len(rendered) > max_characters:
            if not selected:
                raise PipelineInputRejected("INPUT_TOO_LARGE")
            break
        selected.append((block, normalized))
        used += len(rendered)
    if not selected:
        raise PipelineInputRejected("document has no usable text blocks")
    rendered_blocks = [
        f"[页 {block.page_number} 块 {block.block_id}]\n{normalized}"
        for block, normalized in selected
    ]
    input_text = prefix + "\n" + "\n".join(rendered_blocks)
    anchors: dict[str, EvidenceAnchor] = {}
    for block, normalized in selected:
        digest = sha256(
            f"{document_version_id}\x00{block.block_id}\x00{normalized}".encode()
        ).hexdigest()
        evidence_id = f"evidence-{digest[:24]}"
        anchors[evidence_id] = EvidenceAnchor(
            evidence_id=evidence_id,
            document_block_id=block.block_id,
            normalized_text=normalized,
            page_number=block.page_number,
            locator_value=block.locator_value,
        )
    return PreparedDocumentInput(
        text=input_text,
        input_sha256=sha256(input_text.encode()).hexdigest(),
        anchors=anchors,
        block_ids=tuple(block.block_id for block, _ in selected),
    )


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
