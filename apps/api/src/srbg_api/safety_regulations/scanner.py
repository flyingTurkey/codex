"""Deterministic semantic safety scan for untrusted source paragraphs."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol


class ParagraphLike(Protocol):
    @property
    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SemanticSafetyResult:
    passed: bool
    prompt_injection_detected: bool
    resolution_status: str
    scanner_version: str
    input_sha256: str


class RuleBasedSemanticScanner:
    """Fail closed on instruction-like text known to target automated agents."""

    scanner_version = "rules-1.0.0"
    _patterns = (
        re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
        re.compile(r"system\s+prompt", re.IGNORECASE),
        re.compile(r"执行.{0,8}(系统|开发者|工具).{0,8}指令"),
        re.compile(r"忽略.{0,8}(之前|以上).{0,8}指令"),
    )

    def scan(self, paragraphs: Sequence[ParagraphLike]) -> SemanticSafetyResult:
        normalized = "\n".join(paragraph.text for paragraph in paragraphs)
        detected = any(pattern.search(normalized) is not None for pattern in self._patterns)
        return SemanticSafetyResult(
            passed=not detected,
            prompt_injection_detected=detected,
            resolution_status="QUARANTINED" if detected else "NONE",
            scanner_version=self.scanner_version,
            input_sha256=sha256(normalized.encode()).hexdigest(),
        )
