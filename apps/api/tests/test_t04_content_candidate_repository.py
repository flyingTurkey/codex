from pathlib import Path
from uuid import UUID

from srbg_api.intelligence_v2.content_candidate_repository import _claims_from_rows

VERSION_ID = UUID("019f8300-0000-7000-8000-000000000001")


def test_repository_rows_preserve_claim_basis_and_bidirectional_evidence() -> None:
    rows = [
        {
            "claim_id": UUID("019f8300-0000-7000-8000-000000000002"),
            "claim_type": "claimed_outcome",
            "literal_value": "厂商称报警响应缩短",
            "evidence_id": UUID("019f8300-0000-7000-8000-000000000003"),
            "document_version_id": VERSION_ID,
            "document_block_id": UUID("019f8300-0000-7000-8000-000000000004"),
            "locator": "html:p:9",
            "excerpt": "厂商称报警响应缩短。",
            "char_start": 4,
            "char_end": 16,
            "official_first_party": False,
        }
    ]

    claims = _claims_from_rows(rows, document_version_id=VERSION_ID)

    assert len(claims) == 1
    assert claims[0].basis == "MANUFACTURER_CLAIM"
    assert claims[0].evidence[0].locator == "html:p:9"
    assert claims[0].evidence[0].document_version_id == VERSION_ID


def test_repository_marks_authority_reserved_original_only_for_official_source() -> None:
    rows = [
        {
            "claim_id": UUID("019f8300-0000-7000-8000-000000000012"),
            "claim_type": "incident_cause",
            "literal_value": "调查报告认定的直接原因",
            "evidence_id": UUID("019f8300-0000-7000-8000-000000000013"),
            "document_version_id": VERSION_ID,
            "document_block_id": UUID("019f8300-0000-7000-8000-000000000014"),
            "locator": "pdf:page=18&block=2",
            "excerpt": "调查报告认定直接原因为……",
            "char_start": 20,
            "char_end": 35,
            "official_first_party": True,
        }
    ]

    claims = _claims_from_rows(rows, document_version_id=VERSION_ID)

    assert claims[0].basis == "AUTHORITY_FINDING"
    assert claims[0].evidence[0].authority_original is True


def test_repository_has_no_publication_write_capability() -> None:
    source = Path(
        "apps/api/src/srbg_api/intelligence_v2/content_candidate_repository.py"
    ).read_text(encoding="utf-8")

    assert "INSERT INTO content_preparation_candidate_v2" in source
    assert "INSERT INTO content_preparation_invalidation_v2" in source
    assert "INSERT INTO owner_review_case_v2" in source
    assert "UPDATE publication" not in source
    assert "INSERT INTO intelligence_projection_v2" not in source


def test_repository_generates_all_persisted_identifiers_as_uuid7() -> None:
    source = Path(
        "apps/api/src/srbg_api/intelligence_v2/content_candidate_repository.py"
    ).read_text(encoding="utf-8")

    assert "gen_random_uuid" not in source
    assert '"invalidation_id": uuid7()' in source


def test_owner_review_query_exposes_current_or_stale_candidate_and_split_decisions() -> None:
    source = Path(
        "apps/api/src/srbg_api/intelligence_v2/service.py"
    ).read_text(encoding="utf-8")

    assert "content_preparation_candidate_v2" in source
    assert "content_preparation_invalidation_v2" in source
    assert "ACCEPT_CLAIM','REJECT_CLAIM','REPLACE_CLAIM" in source
    assert "APPROVE_AI_SUMMARY','REJECT_AI_SUMMARY','REGENERATE_AI_SUMMARY" in source
    assert "DOCUMENT_VERSION_CHANGED" in source
    assert "ACCEPTED_CLAIMS_CHANGED" in source
    assert "content-preparation-claim-review" in source


def test_existing_content_invalidation_path_appends_t04_stale_fact() -> None:
    source = Path(
        "apps/api/src/srbg_api/publication/repository.py"
    ).read_text(encoding="utf-8")

    assert "content_preparation_invalidation_v2" in source
    assert "SOURCE_WITHDRAWN" in source
    assert "SOURCE_CORRECTED" in source
