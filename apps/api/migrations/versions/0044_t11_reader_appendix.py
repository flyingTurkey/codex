# ruff: noqa: RUF001
"""Expose the fail-closed ReaderAppendix governance read projection.

Revision ID: 0044_t11_reader_appendix
Revises: 0043_t09_hotspot_awards
"""

from collections.abc import Sequence

from alembic import op

revision = "0044_t11_reader_appendix"
down_revision = "0043_t09_hotspot_awards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW reader_appendix_governance_v2 WITH (security_barrier=true) AS
        SELECT projection.event_id,
          projection.appendix_payload,
          COALESCE(evidence.payload,'[]'::jsonb) AS evidence,
          COALESCE(evidence.total_count,0) AS evidence_total,
          COALESCE(automatic_results.payload,'[]'::jsonb) AS automatic_results,
          COALESCE(automatic_results.total_count,0) AS automatic_results_total,
          COALESCE(reviewed_relationships.payload,'[]'::jsonb) AS relationships,
          COALESCE(reviewed_relationships.total_count,0) AS relationships_total,
          COALESCE(automatic_relationships.payload,'[]'::jsonb) AS automatic_relationships,
          COALESCE(automatic_relationships.total_count,0) AS automatic_relationships_total,
          COALESCE(corrections.payload,'[]'::jsonb) AS corrections,
          COALESCE(corrections.total_count,0) AS corrections_total,
          review_context.case_id AS review_case_id
        FROM intelligence_projection_v2 projection
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(row.payload ORDER BY row.created_at,row.id) AS payload,
            max(row.total_count) AS total_count
          FROM (
            SELECT evidence.id,evidence.created_at,count(*) OVER () AS total_count,
              jsonb_build_object(
              'id',evidence.id,
              'claim_ids',jsonb_build_array(evidence.claim_id),
              'document_version_id',evidence.document_version_id,
              'locator',CASE evidence.locator_type
                WHEN 'PDF_TEXT' THEN jsonb_build_object(
                  'type','PDF_TEXT','page_number',evidence.page_number,
                  'block_id',evidence.document_text_block_id,
                  'bbox',jsonb_build_object('x0',evidence.x0_mpt,'y0',evidence.y0_mpt,
                    'x1',evidence.x1_mpt,'y1',evidence.y1_mpt))
                WHEN 'PDF_OCR' THEN jsonb_build_object(
                  'type','PDF_OCR','page_number',evidence.page_number,
                  'block_id',evidence.document_text_block_id,
                  'bbox',jsonb_build_object('x0',evidence.x0_mpt,'y0',evidence.y0_mpt,
                    'x1',evidence.x1_mpt,'y1',evidence.y1_mpt),
                  'confidence_bps',evidence.confidence_bps)
                ELSE NULL END,
              'paragraph_id',evidence.paragraph_id,
              'char_start',evidence.char_start,
              'char_end',evidence.char_end,
              'excerpt',evidence.excerpt,
              'excerpt_sha256',evidence.excerpt_sha256,
              'original_url',evidence.original_url
            ) AS payload
            FROM claim_evidence evidence
            WHERE evidence.document_version_id=projection.document_version_id
              AND evidence.claim_id IN (
                SELECT (claim->>'id')::uuid
                FROM jsonb_array_elements(
                  COALESCE(projection.appendix_payload->'claims','[]'::jsonb)
                ) claim
                WHERE claim->>'decision_status'='ACCEPTED'
              )
              AND (
                (evidence.locator_type IN ('PDF_TEXT','PDF_OCR')
                  AND evidence.page_number IS NOT NULL
                  AND evidence.document_text_block_id IS NOT NULL
                  AND evidence.x0_mpt IS NOT NULL AND evidence.y0_mpt IS NOT NULL
                  AND evidence.x1_mpt IS NOT NULL AND evidence.y1_mpt IS NOT NULL)
                OR (evidence.paragraph_id ~ '^html-p-[0-9]{4}$'
                  AND evidence.char_start IS NOT NULL AND evidence.char_end IS NOT NULL)
              )
            ORDER BY evidence.created_at,evidence.id
            LIMIT 500
          ) row
          GROUP BY row.id IS NOT NULL
        ) evidence ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(row.payload ORDER BY row.updated_at DESC,row.id DESC) AS payload,
            max(row.total_count) AS total_count
          FROM (
            SELECT signal.id,signal.updated_at,count(*) OVER () AS total_count,
              jsonb_strip_nulls(jsonb_build_object(
              'signal_id',signal.id,
              'result_type',signal.result_type,
              'title',signal.payload->>'title',
              'original_url',signal.payload->>'original_url',
              'judgment',signal.payload->'judgment',
              'failure_reason_codes',COALESCE(
                signal.payload->'failure_reason_codes','[]'::jsonb)
            )) AS payload
            FROM personal_signal_projection signal
            WHERE signal.event_id=projection.event_id AND signal.visible
              AND signal.payload ? 'title' AND signal.payload ? 'original_url'
            ORDER BY signal.updated_at DESC,signal.id DESC
            LIMIT 100
          ) row
          GROUP BY row.id IS NOT NULL
        ) automatic_results ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(row.payload ORDER BY row.reviewed_at DESC,row.id DESC) AS payload,
            max(row.total_count) AS total_count
          FROM (
            SELECT relation.id,relation.confirmed_at AS reviewed_at,
              count(*) OVER () AS total_count,jsonb_strip_nulls(
              jsonb_build_object(
                'id',relation.id,'event_id',projection.event_id,
                'from_item_id',COALESCE(relation.source_item_id,source_binding.item_id),
                'to_item_id',COALESCE(relation.target_item_id,target_binding.item_id),
                'relation_type',relation.relation_type,
                'from_stage',source_profile.report_stage,
                'to_stage',target_profile.report_stage,
                'reviewed_by',relation.confirmed_by,
                'reviewed_at',relation.confirmed_at
              )
            ) AS payload
            FROM event_relation relation
            LEFT JOIN LATERAL (
              SELECT binding.item_id FROM event_identity_binding binding
              WHERE binding.event_id=relation.source_event_id ORDER BY binding.created_at LIMIT 1
            ) source_binding ON true
            LEFT JOIN LATERAL (
              SELECT binding.item_id FROM event_identity_binding binding
              WHERE binding.event_id=relation.target_event_id ORDER BY binding.created_at LIMIT 1
            ) target_binding ON true
            LEFT JOIN safety_case_profile source_profile
              ON source_profile.item_id=COALESCE(relation.source_item_id,source_binding.item_id)
            LEFT JOIN safety_case_profile target_profile
              ON target_profile.item_id=COALESCE(relation.target_item_id,target_binding.item_id)
            WHERE relation.event_id=projection.event_id
              OR relation.source_event_id=projection.event_id
              OR relation.target_event_id=projection.event_id
            ORDER BY relation.confirmed_at DESC,relation.id DESC
            LIMIT 500
          ) row
          WHERE row.payload->>'from_item_id' IS NOT NULL
            AND row.payload->>'to_item_id' IS NOT NULL
          GROUP BY row.id IS NOT NULL
        ) reviewed_relationships ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(row.payload ORDER BY row.created_at DESC,row.id DESC) AS payload,
            max(row.total_count) AS total_count
          FROM (
            SELECT decision.id,decision.created_at,count(*) OVER () AS total_count,
              jsonb_strip_nulls(jsonb_build_object(
              'id',decision.id,
              'relationship_key',decision.relationship_key,
              'kind',decision.relationship_kind,
              'source_item_id',decision.source_item_id,
              'target_item_id',decision.target_item_id,
              'status',decision.status,
              'score_bps',decision.score_bps,
              'reason_codes',to_jsonb(decision.reason_codes),
              'algorithm_version',decision.algorithm_version,
              'model_version',decision.model_version,
              'input_fingerprint_sha256',decision.input_fingerprint_sha256,
              'created_at',decision.created_at
            )) AS payload
            FROM automatic_relationship_decision_version decision
            WHERE EXISTS(
              SELECT 1 FROM event_identity_binding binding
              WHERE binding.event_id=projection.event_id
                AND binding.item_id IN (decision.source_item_id,decision.target_item_id)
            )
            ORDER BY decision.created_at DESC,decision.id DESC
            LIMIT 500
          ) row
          GROUP BY row.id IS NOT NULL
        ) automatic_relationships ON true
        LEFT JOIN LATERAL (
          SELECT jsonb_agg(row.payload ORDER BY row.occurred_at DESC,row.id DESC) AS payload,
            count(*) AS total_count
          FROM (
            SELECT invalidation.id,invalidation.created_at AS occurred_at,jsonb_build_object(
              'id',invalidation.id,
              'kind',invalidation.reason,
              'description',CASE invalidation.reason
                WHEN 'DOCUMENT_VERSION_CHANGED' THEN '来源版本变化，依赖内容已失效。'
                WHEN 'ACCEPTED_CLAIMS_CHANGED' THEN '已接受事实变化，依赖内容已失效。'
                WHEN 'SOURCE_WITHDRAWN' THEN '来源已撤回，依赖内容已失效。'
                ELSE '来源已更正，依赖内容已失效。' END,
              'occurred_at',invalidation.created_at,
              'affects',jsonb_build_array('SOURCE_EXCERPT','AI_SUMMARY'),
              'document_version_id',candidate.document_version_id
            ) AS payload
            FROM content_preparation_invalidation_v2 invalidation
            JOIN content_preparation_candidate_v2 candidate
              ON candidate.id=invalidation.candidate_id
            WHERE candidate.event_id=projection.event_id
            UNION ALL
            SELECT correction.id,correction.created_at,jsonb_build_object(
              'id',correction.id,'kind','RELATION_CORRECTED',
              'description',correction.reason,'occurred_at',correction.created_at,
              'affects',jsonb_build_array('RELATIONSHIPS'),
              'document_version_id',NULL
            )
            FROM owner_relationship_correction correction
            WHERE correction.event_id=projection.event_id
            UNION ALL
            SELECT withdrawal.id,withdrawal.created_at,jsonb_build_object(
              'id',withdrawal.id,'kind','RELATION_CORRECTED',
              'description',withdrawal.reason,'occurred_at',withdrawal.created_at,
              'affects',jsonb_build_array('RELATIONSHIPS'),
              'document_version_id',NULL
            )
            FROM owner_relationship_withdrawal withdrawal
            JOIN automatic_relationship_decision_version decision
              ON decision.id=withdrawal.decision_id
            WHERE EXISTS(
              SELECT 1 FROM event_identity_binding binding
              WHERE binding.event_id=projection.event_id
                AND binding.item_id IN (decision.source_item_id,decision.target_item_id)
            )
            ORDER BY occurred_at DESC,id DESC
            LIMIT 100
          ) row
          GROUP BY row.id IS NOT NULL
        ) corrections ON true
        LEFT JOIN LATERAL (
          SELECT review.id AS case_id
          FROM owner_review_case_v2 review
          WHERE review.event_id=projection.event_id
            AND review.document_version_id=projection.document_version_id
            AND review.risk_tier<>'R4'
          ORDER BY review.updated_at DESC,review.id DESC LIMIT 1
        ) review_context ON true
        WHERE projection.projection_kind='FULL'
          AND projection.risk_tier IN ('R1','R2')
        """
    )
    op.execute("REVOKE ALL ON reader_appendix_governance_v2 FROM PUBLIC")
    op.execute("GRANT SELECT ON reader_appendix_governance_v2 TO srbg_projection_reader")


def downgrade() -> None:
    op.execute("DROP VIEW reader_appendix_governance_v2")
