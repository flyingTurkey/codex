"""Opaque keyset cursors bound to one v2 reader surface and filter set."""

from collections.abc import Mapping

from srbg_api.discovery.domain import CursorBindingError, CursorCodec


class InvalidV2Cursor(ValueError):
    """The cursor is malformed, tampered with, or reused on another surface."""


class V2CursorCodec:
    def __init__(self, signing_key: bytes) -> None:
        self._codec = CursorCodec(signing_key)

    @staticmethod
    def _binding(surface: str, filters: Mapping[str, object]) -> dict[str, object]:
        return {"kind": "intelligence-v2", "surface": surface, "filters": dict(filters)}

    def encode(
        self,
        *,
        surface: str,
        sort_values: tuple[str, ...],
        filters: Mapping[str, object],
    ) -> str:
        return self._codec.encode(
            sort_values=sort_values,
            binding=self._binding(surface, filters),
        )

    def decode(
        self,
        value: str,
        *,
        surface: str,
        filters: Mapping[str, object],
        expected_values: int,
    ) -> tuple[str, ...]:
        try:
            decoded = self._codec.decode(value, binding=self._binding(surface, filters))
            if len(decoded) != expected_values:
                raise InvalidV2Cursor("cursor sort shape is invalid")
            return decoded
        except CursorBindingError as exc:
            raise InvalidV2Cursor("invalid v2 cursor") from exc
