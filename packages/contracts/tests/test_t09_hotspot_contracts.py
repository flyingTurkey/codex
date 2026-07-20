from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import HotspotCandidateV2

CLAIM_ID = UUID("019f8400-0000-7000-8000-000000000101")


def test_model_hotspot_candidate_requires_claim_references() -> None:
    candidate = HotspotCandidateV2(
        claim_ids=[CLAIM_ID],
        reasons=[{"text": "权威材料说明工程影响", "claim_ids": [CLAIM_ID]}],
    )

    assert candidate.claim_ids == [CLAIM_ID]


@pytest.mark.parametrize("authority_field", ["awarded", "score", "trigger", "rule_version"])
def test_model_hotspot_candidate_cannot_write_server_authority(authority_field: str) -> None:
    payload = {
        "claim_ids": [str(CLAIM_ID)],
        "reasons": [{"text": "权威材料说明工程影响", "claim_ids": [str(CLAIM_ID)]}],
        authority_field: True,
    }

    with pytest.raises(ValidationError):
        HotspotCandidateV2.model_validate(payload)


def test_model_hotspot_reason_must_reference_candidate_claim() -> None:
    with pytest.raises(ValidationError):
        HotspotCandidateV2.model_validate(
            {
                "claim_ids": [str(CLAIM_ID)],
                "reasons": [
                    {
                        "text": "没有候选 claim 支持",
                        "claim_ids": ["019f8400-0000-7000-8000-000000000999"],
                    }
                ],
            }
        )
