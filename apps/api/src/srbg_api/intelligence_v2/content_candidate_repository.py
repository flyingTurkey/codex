"""PostgreSQL facts for T04 candidates; intentionally has no publication writes."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.content_candidate_service import ContentSummaryRequest
from srbg_api.intelligence_v2.content_candidates import (
    AcceptedClaimInput,
    ClaimBasis,
    ClaimEvidenceInput,
    ContentPreparationCandidate,
    accepted_claim_set_sha256,
    build_source_excerpt,
)

_AUTHORITY_RESERVED = frozenset(
    {
        "regulation_status",
        "incident_cause",
        "responsibility",
        "penalty",
        "corrective_action",
        "final_rectification",
    }
)


def _basis(claim_type: str, *, official_first_party: bool) -> ClaimBasis:
    if claim_type in _AUTHORITY_RESERVED and official_first_party:
        return "AUTHORITY_FINDING"
    if claim_type == "claimed_outcome":
        return "MANUFACTURER_CLAIM"
    if claim_type == "research_conclusion":
        return "RESEARCH_CONCLUSION"
    if claim_type == "verified_outcome":
        return "INDEPENDENT_VERIFICATION"
    return "PROJECT_FIRST_PARTY_RECORD"


def _claims_from_rows(
    rows: Iterable[Mapping[str, Any] | RowMapping], *, document_version_id: UUID
) -> list[AcceptedClaimInput]:
    grouped: dict[UUID, list[ClaimEvidenceInput]] = {}
    facts: dict[UUID, tuple[str, str, bool]] = {}
    for row in rows:
        claim_id = UUID(str(row["claim_id"]))
        official = bool(row["official_first_party"])
        claim_type = str(row["claim_type"])
        facts[claim_id] = (claim_type, str(row["literal_value"]), official)
        grouped.setdefault(claim_id, []).append(
            ClaimEvidenceInput(
                evidence_id=UUID(str(row["evidence_id"])),
                document_version_id=UUID(str(row["document_version_id"])),
                document_block_id=UUID(str(row["document_block_id"])),
                locator=str(row["locator"]),
                excerpt=str(row["excerpt"]),
                char_start=int(row["char_start"]),
                char_end=int(row["char_end"]),
                authority_original=official and claim_type in _AUTHORITY_RESERVED,
            )
        )
    return [
        AcceptedClaimInput(
            claim_id=claim_id,
            document_version_id=document_version_id,
            field_name=facts[claim_id][0],
            value=facts[claim_id][1],
            basis=_basis(facts[claim_id][0], official_first_party=facts[claim_id][2]),
            active=True,
            evidence=tuple(grouped[claim_id]),
        )
        for claim_id in sorted(facts, key=lambda value: value.int)
    ]


class PostgresContentCandidateRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load_active_claims(self, document_version_id: UUID) -> list[AcceptedClaimInput]:
        async with self._engine.connect() as connection:
            rows = [
                dict(row)
                for row in (
                    await connection.execute(
                        text(
                            """
                            SELECT claim.id AS claim_id,claim.claim_type,claim.literal_value,
                              evidence.id AS evidence_id,evidence.document_version_id,
                              evidence.document_text_block_id AS document_block_id,
                              COALESCE(
                                evidence.locator_type||':'||evidence.paragraph_id,
                                evidence.locator_type||':page:'||evidence.page_number,
                                evidence.paragraph_id,
                                'evidence:'||evidence.id
                              ) AS locator,
                              evidence.excerpt,COALESCE(evidence.char_start,0) AS char_start,
                              COALESCE(evidence.char_end,char_length(evidence.excerpt)) AS char_end,
                              source.registry_code LIKE 'GOV-%' AS official_first_party
                            FROM claim
                            JOIN intelligence_item item ON item.id=claim.item_id
                            JOIN source ON source.id=item.source_id
                            JOIN claim_evidence evidence ON evidence.claim_id=claim.id
                            LEFT JOIN LATERAL(
                              SELECT state.state FROM automatic_evidence_fact_state_event state
                              WHERE state.claim_id=claim.id
                              ORDER BY state.created_at DESC,state.id DESC LIMIT 1
                            ) automatic_state ON true
                            WHERE item.current_document_version_id=:version_id
                              AND claim.document_version_id=:version_id
                              AND evidence.document_version_id=:version_id
                              AND evidence.document_text_block_id IS NOT NULL
                              AND claim.verification_status='ACCEPTED'
                              AND (
                                COALESCE(claim.acceptance_method,'HUMAN_REVIEW')
                                  <>'AUTOMATED_EVIDENCE_GATE'
                                OR automatic_state.state='ACTIVE'
                              )
                            ORDER BY claim.id,evidence.id
                            """
                        ),
                        {"version_id": document_version_id},
                    )
                ).mappings()
            ]
        claims = _claims_from_rows(rows, document_version_id=document_version_id)
        if not claims:
            raise RuntimeError("CURRENT_ACTIVE_ACCEPTED_CLAIM_REQUIRED")
        return claims

    async def append_candidate(
        self,
        candidate: ContentPreparationCandidate,
        request: ContentSummaryRequest,
        *,
        create_review_case: bool = True,
    ) -> UUID:
        now = datetime.now(UTC)
        candidate_id = uuid7()
        summary_payload = candidate.summary.model_dump(mode="json") | {
            "visible_character_count": candidate.summary.visible_character_count
        }
        claims_payload = [
            reference.model_dump(mode="json") for reference in candidate.claim_references
        ]
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": f"t04-content:{candidate.document_version_id}"},
            )
            event = (
                (
                    await connection.execute(
                        text(
                            "SELECT binding.event_id,item.title,item.original_url,source.name "
                            "AS source_name FROM intelligence_item item "
                            "JOIN event_identity_binding binding ON binding.item_id=item.id "
                            "JOIN source ON source.id=item.source_id "
                            "WHERE item.current_document_version_id=:version_id"
                        ),
                        {"version_id": candidate.document_version_id},
                    )
                )
                .mappings()
                .one()
            )
            persisted = await connection.scalar(
                text(
                    """
                    INSERT INTO content_preparation_candidate_v2(
                      id,event_id,document_version_id,accepted_claim_set_sha256,
                      source_excerpt,claim_ids,source_excerpt_claim_ids,evidence_locators,
                      claim_basis,claims_payload,summary_payload,visible_character_count,
                      model,prompt_version,schema_version,input_sha256,created_at
                    ) VALUES(
                      :id,:event_id,:version_id,:claim_hash,:excerpt,:claim_ids,
                      :excerpt_claim_ids,:locators,:basis,CAST(:claims AS jsonb),
                      CAST(:summary AS jsonb),:length,:model,:prompt,:schema,:input_hash,:now
                    ) ON CONFLICT(document_version_id,accepted_claim_set_sha256,
                      prompt_version,schema_version,model) DO NOTHING RETURNING id
                    """
                ),
                {
                    "id": candidate_id,
                    "event_id": event["event_id"],
                    "version_id": candidate.document_version_id,
                    "claim_hash": candidate.accepted_claim_set_sha256,
                    "excerpt": candidate.source_excerpt.text,
                    "claim_ids": [value.claim_id for value in candidate.claim_references],
                    "excerpt_claim_ids": list(candidate.source_excerpt.claim_ids),
                    "locators": list(candidate.source_excerpt.evidence_locators),
                    "basis": [value.basis for value in candidate.claim_references],
                    "claims": json.dumps(claims_payload, ensure_ascii=False),
                    "summary": json.dumps(summary_payload, ensure_ascii=False),
                    "length": candidate.summary.visible_character_count,
                    "model": request.model,
                    "prompt": request.prompt_version,
                    "schema": request.schema_version,
                    "input_hash": request.input_sha256,
                    "now": now,
                },
            )
            if persisted is None:
                persisted = await connection.scalar(
                    text(
                        "SELECT id FROM content_preparation_candidate_v2 "
                        "WHERE document_version_id=:version_id "
                        "AND accepted_claim_set_sha256=:claim_hash "
                        "AND prompt_version=:prompt AND schema_version=:schema AND model=:model"
                    ),
                    {
                        "version_id": candidate.document_version_id,
                        "claim_hash": candidate.accepted_claim_set_sha256,
                        "prompt": request.prompt_version,
                        "schema": request.schema_version,
                        "model": request.model,
                    },
                )
            if persisted is None:
                raise RuntimeError("CONTENT_CANDIDATE_NOT_PERSISTED")
            candidate_id = UUID(str(persisted))
            prior_result = await connection.execute(
                text(
                    """
                    SELECT prior.id AS candidate_id,
                      CASE WHEN prior.document_version_id<>:version_id
                        THEN 'DOCUMENT_VERSION_CHANGED'
                        ELSE 'ACCEPTED_CLAIMS_CHANGED' END AS reason
                    FROM content_preparation_candidate_v2 prior
                    WHERE prior.event_id=:event_id AND prior.id<>:candidate_id
                      AND (prior.document_version_id<>:version_id
                        OR prior.accepted_claim_set_sha256<>:claim_hash)
                      AND NOT EXISTS (
                        SELECT 1 FROM content_preparation_invalidation_v2 invalidation
                        WHERE invalidation.candidate_id=prior.id
                      )
                    """
                ),
                {
                    "version_id": candidate.document_version_id,
                    "event_id": event["event_id"],
                    "candidate_id": candidate_id,
                    "claim_hash": candidate.accepted_claim_set_sha256,
                },
            )
            for prior in prior_result.mappings():
                await connection.execute(
                    text(
                        "INSERT INTO content_preparation_invalidation_v2("
                        "id,candidate_id,reason,created_at) "
                        "VALUES(:invalidation_id,:candidate_id,:reason,:now) "
                        "ON CONFLICT(candidate_id) DO NOTHING"
                    ),
                    {
                        "invalidation_id": uuid7(),
                        "candidate_id": prior["candidate_id"],
                        "reason": prior["reason"],
                        "now": now,
                    },
                )
            if create_review_case:
                await connection.execute(
                    text(
                        """
                    INSERT INTO owner_review_case_v2(
                      id,event_id,document_version_id,reason,risk_tier,safe_metadata,
                      state,version,created_at,updated_at
                    ) VALUES(:id,:event_id,:version_id,'CONTENT_PREPARATION_REVIEW','R2',
                      CAST(:metadata AS jsonb),'OPEN',1,:now,:now)
                    ON CONFLICT(document_version_id) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid7(),
                        "event_id": event["event_id"],
                        "version_id": candidate.document_version_id,
                        "metadata": json.dumps(
                            {
                                "title": event["title"],
                                "source_name": event["source_name"],
                                "original_url": event["original_url"],
                            },
                            ensure_ascii=False,
                        ),
                        "now": now,
                    },
                )
        return candidate_id

    async def append_source_excerpt(
        self,
        claims: list[AcceptedClaimInput],
        *,
        document_version_id: UUID,
    ) -> UUID:
        """Persist the evidence-led excerpt independently from model availability."""

        excerpt = build_source_excerpt(claims, current_document_version_id=document_version_id)
        claim_hash = accepted_claim_set_sha256(claims)
        excerpt_id = uuid7()
        async with self._engine.begin() as connection:
            event_id = await connection.scalar(
                text(
                    "SELECT binding.event_id FROM intelligence_item item "
                    "JOIN event_identity_binding binding ON binding.item_id=item.id "
                    "WHERE item.current_document_version_id=:version_id"
                ),
                {"version_id": document_version_id},
            )
            if event_id is None:
                raise RuntimeError("CURRENT_EVENT_REQUIRED")
            persisted = await connection.scalar(
                text(
                    "INSERT INTO source_excerpt_version_v2("
                    "id,event_id,document_version_id,accepted_claim_set_sha256,"
                    "source_excerpt,accepted_claim_ids,source_excerpt_claim_ids,"
                    "evidence_locators,claim_basis,created_at) VALUES("
                    ":id,:event_id,:version_id,:claim_hash,:excerpt,:accepted_ids,"
                    ":excerpt_ids,:locators,:basis,:now) ON CONFLICT("
                    "document_version_id,accepted_claim_set_sha256) DO NOTHING RETURNING id"
                ),
                {
                    "id": excerpt_id,
                    "event_id": event_id,
                    "version_id": document_version_id,
                    "claim_hash": claim_hash,
                    "excerpt": excerpt.text,
                    "accepted_ids": [claim.claim_id for claim in claims],
                    "excerpt_ids": list(excerpt.claim_ids),
                    "locators": list(excerpt.evidence_locators),
                    "basis": list(dict.fromkeys(claim.basis for claim in claims)),
                    "now": datetime.now(UTC),
                },
            )
            if persisted is None:
                persisted = await connection.scalar(
                    text(
                        "SELECT id FROM source_excerpt_version_v2 "
                        "WHERE document_version_id=:version_id "
                        "AND accepted_claim_set_sha256=:claim_hash"
                    ),
                    {"version_id": document_version_id, "claim_hash": claim_hash},
                )
        if persisted is None:
            raise RuntimeError("SOURCE_EXCERPT_NOT_PERSISTED")
        return UUID(str(persisted))

    async def append_invalidation(self, candidate_id: UUID, reason: str) -> None:
        async with self._engine.begin() as connection:
            result = await connection.execute(
                text(
                    "INSERT INTO content_preparation_invalidation_v2("
                    "id,candidate_id,reason,created_at) VALUES(:id,:candidate_id,:reason,:now) "
                    "ON CONFLICT(candidate_id) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "candidate_id": candidate_id,
                    "reason": reason,
                    "now": datetime.now(UTC),
                },
            )
            if result.rowcount not in {0, 1}:
                raise RuntimeError("CONTENT_INVALIDATION_NOT_PERSISTED")
