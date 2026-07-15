"""Pure Round 10 domain rules shared by HTTP and persistence adapters."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

SearchMatchKind = Literal["EXACT_IDENTIFIER", "TITLE_ENTITY_TAG", "BODY", "SEMANTIC"]
_MATCH_TIER: Mapping[SearchMatchKind, int] = {
    "EXACT_IDENTIFIER": 0,
    "TITLE_ENTITY_TAG": 1,
    "BODY": 2,
    "SEMANTIC": 3,
}
_BRACKETS = str.maketrans(
    {
        "\u3014": "[",
        "\u3015": "]",
        "\u3010": "[",
        "\u3011": "]",
        "\uff08": "(",
        "\uff09": ")",
    }
)
_FORMULA_PREFIXES = frozenset("=+-@")


class CursorBindingError(ValueError):
    """Raised when an opaque cursor is malformed, tampered with, or reused."""


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    item_id: UUID
    match_kind: SearchMatchKind
    score: int
    activity_at: datetime


def normalize_identifier(value: str) -> str:
    """Normalize DOI/document identifiers without inventing missing characters."""

    normalized = unicodedata.normalize("NFKC", value).translate(_BRACKETS).strip()
    lowered = normalized.casefold()
    for prefix in ("doi:", "https://doi.org/", "http://doi.org/", "https://dx.doi.org/"):
        position = lowered.find(prefix)
        if position >= 0:
            normalized = normalized[position + len(prefix) :]
            lowered = normalized.casefold()
    return re.sub(r"\s+", "", normalized).casefold()


def normalize_search_query(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).strip()
    return tuple(part for part in re.split(r"[+\s]+", normalized) if part)


def tokenize_chinese_text(value: str) -> str:
    """Produce deterministic words and CJK bigrams for PostgreSQL simple FTS."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    tokens: list[str] = []
    for segment in re.findall(r"[\u3400-\u9fff]+|[a-z0-9][a-z0-9._/-]*", normalized):
        tokens.append(segment)
        if re.fullmatch(r"[\u3400-\u9fff]+", segment) and len(segment) > 1:
            tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
    return " ".join(dict.fromkeys(tokens))


def rank_search_candidates(candidates: Sequence[SearchCandidate]) -> list[SearchCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            _MATCH_TIER[candidate.match_kind],
            -candidate.score,
            -candidate.activity_at.timestamp(),
            candidate.item_id.int,
        ),
    )


def escape_spreadsheet_formula(value: str) -> str:
    leading_length = len(value) - len(value.lstrip())
    if leading_length < len(value) and value[leading_length] in _FORMULA_PREFIXES:
        return value[:leading_length] + "'" + value[leading_length:]
    return value


class CursorCodec:
    """Versioned HMAC cursor bound to normalized query, filters, sort, and ACL."""

    def __init__(self, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ValueError("cursor signing key must contain at least 32 bytes")
        self._key = signing_key

    def encode(self, *, sort_values: tuple[str, ...], binding: Mapping[str, object]) -> str:
        body = {
            "v": 1,
            "s": list(sort_values),
            "b": self._binding_digest(binding),
        }
        encoded_body = self._b64(self._canonical(body))
        signature = self._b64(hmac.digest(self._key, encoded_body.encode("ascii"), "sha256"))
        return f"{encoded_body}.{signature}"

    def decode(self, value: str, *, binding: Mapping[str, object]) -> tuple[str, ...]:
        try:
            encoded_body, encoded_signature = value.split(".", maxsplit=1)
            expected = self._b64(hmac.digest(self._key, encoded_body.encode("ascii"), "sha256"))
            if not hmac.compare_digest(encoded_signature, expected):
                raise CursorBindingError("cursor signature is invalid")
            body = json.loads(self._unb64(encoded_body))
            if body.get("v") != 1 or body.get("b") != self._binding_digest(binding):
                raise CursorBindingError("cursor does not belong to this query")
            sort_values = body.get("s")
            if not isinstance(sort_values, list) or not all(
                isinstance(entry, str) for entry in sort_values
            ):
                raise CursorBindingError("cursor sort values are invalid")
            return tuple(sort_values)
        except CursorBindingError:
            raise
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise CursorBindingError("cursor is malformed") from exc

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def _binding_digest(cls, binding: Mapping[str, object]) -> str:
        return hashlib.sha256(cls._canonical(binding)).hexdigest()

    @staticmethod
    def _b64(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _unb64(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
