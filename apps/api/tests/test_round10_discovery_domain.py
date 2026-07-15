from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.discovery.domain import (
    CursorBindingError,
    CursorCodec,
    SearchCandidate,
    escape_spreadsheet_formula,
    normalize_identifier,
    normalize_search_query,
    rank_search_candidates,
)


def test_normalizes_document_numbers_doi_and_chinese_and_query() -> None:
    fullwidth_doi = "\uff24\uff2f\uff29\uff1a https://doi.org/10.1000/ABC-12 "
    document_number = "川交规\u30142026\u3015 10 号"
    combination = " 隧道\uff0b监测预警 + 四川 "
    assert normalize_identifier(fullwidth_doi) == "10.1000/abc-12"
    assert normalize_identifier(document_number) == "川交规[2026]10号"
    assert normalize_search_query(combination) == ("隧道", "监测预警", "四川")


def test_exact_identifier_always_ranks_before_semantic_candidate() -> None:
    exact = SearchCandidate(
        item_id=UUID("019b0000-0000-7000-8000-000000001001"),
        match_kind="EXACT_IDENTIFIER",
        score=1,
        activity_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    semantic = SearchCandidate(
        item_id=UUID("019b0000-0000-7000-8000-000000001002"),
        match_kind="SEMANTIC",
        score=10000,
        activity_at=datetime(2026, 7, 15, tzinfo=UTC),
    )

    assert rank_search_candidates([semantic, exact]) == [exact, semantic]


def test_cursor_is_signed_and_bound_to_query_acl_and_sort() -> None:
    codec = CursorCodec(b"round10-test-key-with-at-least-32-bytes")
    cursor = codec.encode(
        sort_values=("2026-07-15T00:00:00+00:00", "019b0000-0000-7000-8000-000000001001"),
        binding={"query": "隧道", "roles": ["viewer"], "sort": "latest"},
    )

    assert codec.decode(
        cursor,
        binding={"query": "隧道", "roles": ["viewer"], "sort": "latest"},
    ) == ("2026-07-15T00:00:00+00:00", "019b0000-0000-7000-8000-000000001001")
    with pytest.raises(CursorBindingError):
        codec.decode(cursor, binding={"query": "桥梁", "roles": ["viewer"], "sort": "latest"})
    with pytest.raises(CursorBindingError):
        codec.decode(
            cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
            binding={"query": "隧道", "roles": ["viewer"], "sort": "latest"},
        )


@pytest.mark.parametrize("value", ["=2+2", "+SUM(A1:A2)", " -1+2", "\t@cmd"])
def test_export_escapes_spreadsheet_formula_prefixes(value: str) -> None:
    assert escape_spreadsheet_formula(value).lstrip().startswith("'")
