# ruff: noqa: E501
"""PERS-06 automatic evidence facts and isolated AI judgments.

Revision ID: 0026_automatic_evidence_facts
Revises: 0025_personal_source_discovery
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_automatic_evidence_facts"
down_revision = "0025_personal_source_discovery"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("claim", sa.Column("acceptance_method", sa.String(40)))
    op.create_check_constraint(
        "ck_claim_acceptance_method",
        "claim",
        "acceptance_method IS NULL OR acceptance_method IN "
        "('HUMAN_REVIEW','AUTOMATED_EVIDENCE_GATE')",
    )
    op.drop_constraint("ck_ai_pipeline_status", "ai_pipeline_run", type_="check")
    op.create_check_constraint(
        "ck_ai_pipeline_status",
        "ai_pipeline_run",
        "status IN ('QUEUED','PREPARING','CLASSIFYING','EXTRACTING','EVIDENCE_GATING',"
        "'WAITING_CLAIM_REVIEW','RUNNING','SUCCEEDED','FAILED','DEGRADED')",
    )
    op.create_table(
        "automatic_evidence_acceptance",
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column("acceptance_method", sa.String(40), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column(
            "input_document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence_set_sha256", sa.String(64), nullable=False),
        sa.Column("system_actor_id", _uuid(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "acceptance_method='AUTOMATED_EVIDENCE_GATE'", name="ck_automatic_acceptance_method"
        ),
        sa.CheckConstraint(
            "evidence_set_sha256 ~ '^[0-9a-f]{64}$'", name="ck_automatic_acceptance_hash"
        ),
    )
    op.create_table(
        "automatic_evidence_fact_state_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('ACTIVE','INVALIDATED')", name="ck_automatic_fact_state"),
        sa.UniqueConstraint(
            "claim_id", "state", "reason_code", name="uq_automatic_fact_state_reason"
        ),
    )
    op.create_index(
        "ix_automatic_fact_state_claim_created",
        "automatic_evidence_fact_state_event",
        ["claim_id", "created_at"],
    )
    op.create_table(
        "ai_judgment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("step_run_id", _uuid(), sa.ForeignKey("ai_step_run.id", ondelete="RESTRICT")),
        sa.Column("model_candidate_id", sa.String(200), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("candidate_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_bps", sa.Integer(), nullable=False),
        sa.Column("attribution", sa.String(500)),
        sa.Column("origin", sa.String(20), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("evidence_set_sha256", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "document_version_id",
            "model_candidate_id",
            "origin",
            name="uq_ai_judgment_version_candidate",
        ),
        sa.CheckConstraint("confidence_bps BETWEEN 0 AND 10000", name="ck_ai_judgment_confidence"),
        sa.CheckConstraint("origin IN ('MODEL','LOCAL_RULE')", name="ck_ai_judgment_origin"),
        sa.CheckConstraint("status IN ('CURRENT','INVALIDATED')", name="ck_ai_judgment_status"),
        sa.CheckConstraint(
            "evidence_set_sha256 IS NULL OR evidence_set_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_ai_judgment_hash",
        ),
    )
    op.create_table(
        "ai_judgment_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "judgment_id",
            _uuid(),
            sa.ForeignKey("ai_judgment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_text_block_id",
            _uuid(),
            sa.ForeignKey("document_text_block.id", ondelete="RESTRICT"),
        ),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_sha256", sa.String(64), nullable=False),
        sa.Column("locator", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "excerpt_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ai_judgment_evidence_hash"
        ),
    )
    op.create_table(
        "personal_content_outbox",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "document_version_id", "action", name="uq_personal_content_version_action"
        ),
        sa.CheckConstraint(
            "action IN ('PROJECT','INVALIDATE','REPROCESS')", name="ck_personal_content_action"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED')",
            name="ck_personal_content_status",
        ),
    )
    op.create_table(
        "personal_content_projection",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.Column("evidence_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("generation>=1", name="ck_personal_content_projection_generation"),
    )
    op.execute(
        "CREATE FUNCTION forbid_new_claim_review_task() RETURNS trigger LANGUAGE plpgsql "
        "SET search_path=pg_catalog,public AS $$ BEGIN IF NEW.task_type='CLAIM_REVIEW' THEN "
        "RAISE EXCEPTION 'PERS06_CLAIM_REVIEW_READ_ONLY'; END IF; RETURN NEW; END $$"
    )
    op.execute("REVOKE ALL ON FUNCTION forbid_new_claim_review_task() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_forbid_new_claim_review_task BEFORE INSERT ON review_task "
        "FOR EACH ROW EXECUTE FUNCTION forbid_new_claim_review_task()"
    )
    op.execute(
        r"""
        CREATE FUNCTION invalidate_automatic_evidence_for_version(
          p_version_id uuid,p_reason text,p_now timestamptz
        ) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_count integer;
        BEGIN
          INSERT INTO automatic_evidence_fact_state_event(
            id,claim_id,state,reason_code,actor_id,created_at
          )
          SELECT source_automation_derived_uuid(claim.id,'pers06-invalid-'||p_reason),
                 claim.id,'INVALIDATED',left(p_reason,100),
                 '019b0000-0000-7000-8000-000000009002'::uuid,p_now
          FROM claim JOIN automatic_evidence_acceptance acceptance
            ON acceptance.claim_id=claim.id
          WHERE acceptance.input_document_version_id=p_version_id
            AND 'ACTIVE'=(SELECT state.state
              FROM automatic_evidence_fact_state_event state
              WHERE state.claim_id=claim.id
              ORDER BY state.created_at DESC,state.id DESC LIMIT 1)
          ON CONFLICT(claim_id,state,reason_code) DO NOTHING;
          GET DIAGNOSTICS v_count=ROW_COUNT;
          UPDATE ai_judgment SET status='INVALIDATED',invalidated_at=p_now
           WHERE document_version_id=p_version_id AND status='CURRENT';
          INSERT INTO personal_content_outbox(
            id,document_version_id,item_id,action,status,attempt_count,
            available_at,created_at,processed_at
          )
          SELECT source_automation_derived_uuid(item.id,'pers06-invalidate-'||p_reason),
                 p_version_id,item.id,'INVALIDATE','PENDING',0,p_now,p_now,NULL
          FROM intelligence_item item
          WHERE item.current_document_version_id=p_version_id
             OR EXISTS(SELECT 1 FROM claim WHERE claim.item_id=item.id
                       AND claim.document_version_id=p_version_id)
          ON CONFLICT(document_version_id,action) DO NOTHING;
          RETURN v_count;
        END $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION invalidate_automatic_evidence_for_version(uuid,text,timestamptz) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION invalidate_automatic_evidence_for_version(uuid,text,timestamptz) TO srbg_worker_role,srbg_publication_writer"
    )
    op.execute(
        r"""
        CREATE FUNCTION pers06_document_version_changed() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        BEGIN
          IF OLD.current_version_id IS DISTINCT FROM NEW.current_version_id
             AND OLD.current_version_id IS NOT NULL THEN
            PERFORM invalidate_automatic_evidence_for_version(
              OLD.current_version_id,'DOCUMENT_VERSION_CHANGED',statement_timestamp());
            INSERT INTO source_content_outbox(
              id,document_version_id,pipeline_run_id,status,attempt_count,
              available_at,last_error_code,created_at,updated_at
            ) VALUES(
              source_automation_derived_uuid(NEW.current_version_id,'pers06-reprocess'),
              NEW.current_version_id,NULL,'PENDING',0,statement_timestamp(),NULL,
              statement_timestamp(),statement_timestamp())
            ON CONFLICT(document_version_id) DO NOTHING;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION pers06_document_version_changed() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_pers06_document_version_changed AFTER UPDATE OF current_version_id ON document FOR EACH ROW EXECUTE FUNCTION pers06_document_version_changed()"
    )
    op.execute(
        r"""
        CREATE FUNCTION pers06_content_lifecycle_invalidated() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE v_version_id uuid;
        BEGIN
          IF NEW.state IN ('WITHDRAWN','SUPERSEDED') THEN
            IF NEW.target_type='CLAIM' THEN
              SELECT claim.document_version_id INTO v_version_id
                FROM claim WHERE claim.id=NEW.target_id;
            ELSIF NEW.target_type='SUMMARY' THEN
              SELECT summary.document_version_id INTO v_version_id
                FROM derived_summary summary WHERE summary.id=NEW.target_id;
            ELSIF NEW.target_type='ITEM' THEN
              SELECT item.current_document_version_id INTO v_version_id
                FROM intelligence_item item WHERE item.id=NEW.target_id;
            END IF;
            IF v_version_id IS NOT NULL THEN
              PERFORM invalidate_automatic_evidence_for_version(
                v_version_id,'DOCUMENT_'||NEW.state,NEW.created_at);
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION pers06_content_lifecycle_invalidated() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_pers06_content_lifecycle_invalidated AFTER INSERT ON content_lifecycle_event FOR EACH ROW EXECUTE FUNCTION pers06_content_lifecycle_invalidated()"
    )
    for table in (
        "automatic_evidence_acceptance",
        "automatic_evidence_fact_state_event",
        "ai_judgment_evidence",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_pers06_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
        )
    op.execute(
        "GRANT SELECT,INSERT ON automatic_evidence_acceptance,automatic_evidence_fact_state_event,ai_judgment,ai_judgment_evidence,personal_content_outbox TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON automatic_evidence_acceptance,automatic_evidence_fact_state_event,ai_judgment,ai_judgment_evidence TO srbg_runtime"
    )
    op.execute("GRANT SELECT,UPDATE ON personal_content_outbox TO srbg_publication_writer")
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON personal_content_projection TO srbg_publication_writer"
    )
    op.execute("GRANT SELECT ON personal_content_projection TO srbg_runtime,srbg_projection_reader")


def downgrade() -> None:
    bind = op.get_bind()
    materialized = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM automatic_evidence_acceptance) OR EXISTS(SELECT 1 FROM ai_judgment) OR EXISTS(SELECT 1 FROM personal_content_outbox)"
        )
    ).scalar_one()
    if materialized:
        raise RuntimeError("0026_DOWNGRADE_BLOCKED: automatic content facts exist")
    op.execute("DROP TRIGGER IF EXISTS trg_forbid_new_claim_review_task ON review_task")
    op.execute("DROP FUNCTION IF EXISTS forbid_new_claim_review_task()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_pers06_content_lifecycle_invalidated ON content_lifecycle_event"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_pers06_document_version_changed ON document")
    op.execute("DROP FUNCTION IF EXISTS pers06_content_lifecycle_invalidated()")
    op.execute("DROP FUNCTION IF EXISTS pers06_document_version_changed()")
    op.execute(
        "DROP FUNCTION IF EXISTS invalidate_automatic_evidence_for_version(uuid,text,timestamptz)"
    )
    for table in (
        "automatic_evidence_acceptance",
        "automatic_evidence_fact_state_event",
        "ai_judgment_evidence",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_pers06_append_only ON {table}")
    for table in (
        "personal_content_projection",
        "personal_content_outbox",
        "ai_judgment_evidence",
        "ai_judgment",
        "automatic_evidence_fact_state_event",
        "automatic_evidence_acceptance",
    ):
        op.drop_table(table)
    op.drop_constraint("ck_ai_pipeline_status", "ai_pipeline_run", type_="check")
    op.create_check_constraint(
        "ck_ai_pipeline_status",
        "ai_pipeline_run",
        "status IN ('QUEUED','PREPARING','CLASSIFYING','EXTRACTING','WAITING_CLAIM_REVIEW','RUNNING','SUCCEEDED','FAILED','DEGRADED')",
    )
    op.drop_constraint("ck_claim_acceptance_method", "claim", type_="check")
    op.drop_column("claim", "acceptance_method")
