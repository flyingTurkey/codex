"""Server-side input assembly for the four independent AI tasks."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from srbg_api.ai_pipeline.contracts import EvidenceAnchor


class PipelineInputRejected(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptedClaim:
    claim_id: str
    field: str
    value: Any


class AiPipeline:
    """Builds minimal prompts; persistence and publishing remain outside the model worker."""

    def build_summary_prompt(self, claims: list[AcceptedClaim]) -> str:
        if not claims:
            raise PipelineInputRejected("summary requires at least one accepted claim")
        payload = [
            {"claim_id": claim.claim_id, "field": claim.field, "value": claim.value}
            for claim in claims
        ]
        return "<accepted_claims>\n" + json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n</accepted_claims>"

    def validate_summary_claims(
        self, used_claim_ids: list[str], accepted_claims: list[AcceptedClaim]
    ) -> None:
        accepted_ids = {claim.claim_id for claim in accepted_claims}
        if not used_claim_ids or not set(used_claim_ids).issubset(accepted_ids):
            raise PipelineInputRejected("summary references a non-accepted claim")

    def issue_evidence_anchors(
        self, *, document_version_id: str, blocks: dict[str, str]
    ) -> dict[str, EvidenceAnchor]:
        anchors: dict[str, EvidenceAnchor] = {}
        for block_id, text in blocks.items():
            normalized = re.sub(r"\s+", " ", text).strip()
            digest = sha256(
                f"{document_version_id}\x00{block_id}\x00{normalized}".encode()
            ).hexdigest()
            evidence_id = f"evidence-{digest[:24]}"
            anchors[evidence_id] = EvidenceAnchor(
                evidence_id=evidence_id,
                document_block_id=block_id,
                normalized_text=normalized,
            )
        return anchors
