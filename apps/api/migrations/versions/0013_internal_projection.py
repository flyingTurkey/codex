"""Round 13 event identity and isolated internal publication projection.

Revision ID: 0013_internal_projection
Revises: 0012_operations_readiness
"""

# ruff: noqa: E501 -- PostgreSQL DDL signatures and foreign-key clauses stay auditable inline.

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_internal_projection"
down_revision = "0012_operations_readiness"
branch_labels = None
depends_on = None

ROUND13_TABLES = (
    "event_identity_binding",
    "projection_build_run",
    "event_projection_revision",
    "event_projection_field_source",
    "projection_reconciliation_difference",
    "audit_chain_anchor",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _add_independent_policy_axes()
    _create_identity_and_reconciliation_tables()
    _create_projection_schema()
    _create_controlled_audit_boundary()
    _create_projection_invalidation_trigger()
    _configure_projection_roles()


def _add_independent_policy_axes() -> None:
    op.add_column(
        "intelligence_item",
        sa.Column("publication_risk_tier", sa.String(2), nullable=True),
    )
    op.add_column(
        "intelligence_item",
        sa.Column(
            "content_severity", sa.String(12), nullable=False, server_default="UNASSESSED"
        ),
    )
    op.add_column(
        "intelligence_item",
        sa.Column("projection_level", sa.String(20), nullable=False, server_default="NONE"),
    )
    op.execute("UPDATE intelligence_item SET publication_risk_tier = risk_level")
    op.alter_column("intelligence_item", "publication_risk_tier", nullable=False)
    op.create_check_constraint(
        "ck_item_publication_risk_tier",
        "intelligence_item",
        "publication_risk_tier IN ('R1','R2','R3','R4')",
    )
    op.create_check_constraint(
        "ck_item_legacy_risk_compatibility",
        "intelligence_item",
        "publication_risk_tier = risk_level",
    )
    op.create_check_constraint(
        "ck_item_content_severity",
        "intelligence_item",
        "content_severity IN ('UNASSESSED','LOW','MODERATE','HIGH','CRITICAL')",
    )
    op.create_check_constraint(
        "ck_item_projection_level",
        "intelligence_item",
        "projection_level IN ('NONE','METADATA_ONLY','FULL')",
    )
    op.create_check_constraint(
        "ck_item_r4_no_projection",
        "intelligence_item",
        "publication_risk_tier <> 'R4' OR projection_level = 'NONE'",
    )
    op.execute(
        """
        CREATE FUNCTION sync_publication_risk_tier() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.publication_risk_tier IS NULL THEN
            NEW.publication_risk_tier := NEW.risk_level;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_sync_publication_risk_tier "
        "BEFORE INSERT OR UPDATE OF risk_level, publication_risk_tier ON intelligence_item "
        "FOR EACH ROW EXECUTE FUNCTION sync_publication_risk_tier()"
    )


def _create_identity_and_reconciliation_tables() -> None:
    op.create_table(
        "event_identity_binding",
        sa.Column(
            "event_id",
            _uuid(),
            sa.ForeignKey("event.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("binding_kind", sa.String(30), nullable=False),
        sa.Column("source_decision_id", _uuid()),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "binding_kind IN ('CONFIRMED_MEMBERSHIP','ROUND13_ONE_TO_ONE')",
            name="ck_event_identity_binding_kind",
        ),
    )
    op.create_index("ix_event_identity_binding_event", "event_identity_binding", ["event_id"])
    op.create_table(
        "projection_reconciliation_difference",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("build_run_id", _uuid(), nullable=False),
        sa.Column("event_id", _uuid()),
        sa.Column("item_id", _uuid()),
        sa.Column("difference_code", sa.String(80), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "build_run_id", "item_id", "difference_code", name="uq_projection_difference"
        ),
    )
    op.create_table(
        "audit_chain_anchor",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("audit_log_id", _uuid(), sa.ForeignKey("audit_log.id"), nullable=False, unique=True),
        sa.Column("entry_hash", sa.String(64), nullable=False),
        sa.Column("anchor_store", sa.String(100), nullable=False),
        sa.Column("anchor_object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("anchored_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("entry_hash ~ '^[0-9a-f]{64}$'", name="ck_audit_anchor_hash"),
    )


def _create_projection_schema() -> None:
    op.execute("CREATE SCHEMA published_v1")
    op.create_table(
        "projection_build_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("generation", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("projection_version", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("projected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("difference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_reason", sa.String(500)),
        sa.CheckConstraint("generation >= 1", name="ck_projection_build_generation"),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED')", name="ck_projection_build_status"
        ),
        schema="published_v1",
    )
    op.create_table(
        "event_projection_revision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), nullable=False),
        sa.Column("item_id", _uuid(), nullable=False),
        sa.Column("publication_revision_id", _uuid()),
        sa.Column("build_run_id", _uuid(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("projection_version", sa.String(20), nullable=False),
        sa.Column("publication_risk_tier", sa.String(2), nullable=False),
        sa.Column("content_severity", sa.String(12), nullable=False),
        sa.Column("projection_level", sa.String(20), nullable=False),
        sa.Column("allowed_surfaces", postgresql.ARRAY(sa.String(30)), nullable=False),
        sa.Column("summary_payload", postgresql.JSONB(), nullable=False),
        sa.Column("detail_payload", postgresql.JSONB()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("invalidation_reason", sa.String(80)),
        sa.Column("audit_log_id", _uuid()),
        sa.UniqueConstraint("event_id", "generation", name="uq_event_projection_generation"),
        sa.CheckConstraint(
            "publication_risk_tier IN ('R1','R2','R3','R4')", name="ck_projection_risk"
        ),
        sa.CheckConstraint(
            "content_severity IN ('UNASSESSED','LOW','MODERATE','HIGH','CRITICAL')",
            name="ck_projection_severity",
        ),
        sa.CheckConstraint(
            "projection_level IN ('METADATA_ONLY','FULL')", name="ck_projection_level"
        ),
        sa.CheckConstraint("publication_risk_tier <> 'R4'", name="ck_projection_no_r4"),
        sa.CheckConstraint(
            "projection_level <> 'METADATA_ONLY' OR detail_payload IS NULL",
            name="ck_projection_metadata_no_detail",
        ),
        sa.CheckConstraint(
            "state IN ('ACTIVE','INVALIDATED')", name="ck_projection_state"
        ),
        schema="published_v1",
    )
    op.create_index(
        "ix_event_projection_current",
        "event_projection_revision",
        ["event_id", "generation"],
        schema="published_v1",
    )
    op.create_table(
        "event_projection_field_source",
        sa.Column("projection_revision_id", _uuid(), primary_key=True),
        sa.Column("field_name", sa.String(100), primary_key=True),
        sa.Column("claim_id", _uuid()),
        sa.Column("evidence_id", _uuid()),
        sa.Column("document_version_id", _uuid(), nullable=False),
        sa.Column("publication_revision_id", _uuid()),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("source_sha256 ~ '^[0-9a-f]{64}$'", name="ck_projection_field_hash"),
        schema="published_v1",
    )
    op.execute(
        """
        ALTER TABLE published_v1.event_projection_revision
          ADD CONSTRAINT fk_projection_event FOREIGN KEY (event_id) REFERENCES public.event(id),
          ADD CONSTRAINT fk_projection_item FOREIGN KEY (item_id) REFERENCES public.intelligence_item(id),
          ADD CONSTRAINT fk_projection_publication_revision FOREIGN KEY (publication_revision_id) REFERENCES public.publication_revision(id),
          ADD CONSTRAINT fk_projection_build FOREIGN KEY (build_run_id) REFERENCES published_v1.projection_build_run(id),
          ADD CONSTRAINT fk_projection_audit FOREIGN KEY (audit_log_id) REFERENCES public.audit_log(id)
        """
    )
    op.execute(
        """
        ALTER TABLE published_v1.event_projection_field_source
          ADD CONSTRAINT fk_projection_field_revision FOREIGN KEY (projection_revision_id) REFERENCES published_v1.event_projection_revision(id) ON DELETE CASCADE,
          ADD CONSTRAINT fk_projection_field_claim FOREIGN KEY (claim_id) REFERENCES public.claim(id),
          ADD CONSTRAINT fk_projection_field_evidence FOREIGN KEY (evidence_id) REFERENCES public.claim_evidence(id),
          ADD CONSTRAINT fk_projection_field_document_version FOREIGN KEY (document_version_id) REFERENCES public.document_version(id),
          ADD CONSTRAINT fk_projection_field_publication_revision FOREIGN KEY (publication_revision_id) REFERENCES public.publication_revision(id)
        """
    )
    op.execute(
        """
        ALTER TABLE public.projection_reconciliation_difference
          ADD CONSTRAINT fk_projection_difference_build FOREIGN KEY (build_run_id) REFERENCES published_v1.projection_build_run(id) ON DELETE CASCADE,
          ADD CONSTRAINT fk_projection_difference_event FOREIGN KEY (event_id) REFERENCES public.event(id),
          ADD CONSTRAINT fk_projection_difference_item FOREIGN KEY (item_id) REFERENCES public.intelligence_item(id)
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.current_event_summary AS
        SELECT DISTINCT ON (event_id) event_id, generation, projection_version,
               publication_revision_id, projection_level, summary_payload, generated_at
          FROM published_v1.event_projection_revision
         WHERE state = 'ACTIVE'
         ORDER BY event_id, generation DESC
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.current_event_detail AS
        SELECT DISTINCT ON (event_id) event_id, generation, projection_version,
               publication_revision_id, detail_payload, generated_at
          FROM published_v1.event_projection_revision
         WHERE state = 'ACTIVE' AND projection_level = 'FULL'
         ORDER BY event_id, generation DESC
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.title_search AS
        SELECT event_id, generation, summary_payload->>'title' AS title,
               summary_payload->>'content_type' AS content_type,
               summary_payload->>'domain' AS domain
          FROM published_v1.current_event_summary
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.distribution_candidates AS
        SELECT event_id, generation, allowed_surfaces, summary_payload
          FROM published_v1.event_projection_revision
         WHERE state = 'ACTIVE' AND projection_level = 'FULL'
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.fulltext_export AS
        SELECT event_id, generation, detail_payload
          FROM published_v1.event_projection_revision
         WHERE state = 'ACTIVE' AND projection_level = 'FULL'
           AND 'FULLTEXT_EXPORT' = ANY(allowed_surfaces)
        """
    )


def _create_controlled_audit_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION append_audit_event(
            p_id uuid, p_event_type text, p_actor_id uuid, p_target_type text, p_target_id uuid,
            p_before_state jsonb, p_after_state jsonb, p_reason text, p_request_id text,
            p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
            v_id uuid := p_id;
            v_previous_hash text;
            v_entry_hash text;
        BEGIN
            IF substring(v_id::text, 15, 1) <> '7' THEN
                RAISE EXCEPTION 'audit event id must be UUIDv7';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtext('audit_log'));
            SELECT entry_hash INTO v_previous_hash FROM public.audit_log
             ORDER BY created_at DESC, id DESC LIMIT 1;
            v_entry_hash := encode(digest(convert_to(
                jsonb_build_object(
                    'id', v_id::text, 'event_type', p_event_type, 'actor_id', p_actor_id::text,
                    'target_type', p_target_type, 'target_id', p_target_id::text,
                    'before_state', p_before_state, 'after_state', p_after_state,
                    'reason', p_reason, 'request_id', p_request_id,
                    'previous_hash', v_previous_hash, 'created_at', p_created_at
                )::text, 'UTF8'), 'sha256'), 'hex');
            INSERT INTO public.audit_log (
                id, event_type, actor_id, target_type, target_id, before_state, after_state,
                reason, request_id, previous_hash, entry_hash, created_at
            ) VALUES (
                v_id, p_event_type, p_actor_id, p_target_type, p_target_id, p_before_state,
                p_after_state, p_reason, p_request_id, v_previous_hash, v_entry_hash, p_created_at
            );
            RETURN v_id;
        END $$
        """
    )
    signature = "append_audit_event(uuid,text,uuid,text,uuid,jsonb,jsonb,text,text,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON audit_log FROM srbg_runtime")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON audit_log FROM srbg_publication_writer")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_runtime, srbg_publication_writer"
    )


def _create_projection_invalidation_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION invalidate_event_projection_on_publication_change() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public, published_v1 AS $$
        BEGIN
          IF NEW.status IS DISTINCT FROM OLD.status
             OR NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id THEN
            UPDATE published_v1.event_projection_revision
               SET state = 'INVALIDATED', invalidated_at = now(),
                   invalidation_reason = CASE
                     WHEN NEW.status = 'WITHDRAWN' THEN 'PUBLICATION_WITHDRAWN'
                     ELSE 'PUBLICATION_REVISION_CHANGED' END
             WHERE item_id = NEW.item_id AND state = 'ACTIVE';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_invalidate_event_projection_on_publication_change "
        "AFTER UPDATE OF status, current_revision_id ON publication FOR EACH ROW "
        "EXECUTE FUNCTION invalidate_event_projection_on_publication_change()"
    )


def _configure_projection_roles() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_projection_reader') THEN
            CREATE ROLE srbg_projection_reader NOLOGIN;
          END IF;
        END $$
        """
    )
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA public FROM srbg_projection_reader")
    op.execute(
        "GRANT USAGE ON SCHEMA public TO srbg_runtime, srbg_publication_writer, srbg_admin_role"
    )
    op.execute("REVOKE ALL ON SCHEMA published_v1 FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA published_v1 TO srbg_projection_reader")
    op.execute(
        "GRANT SELECT ON published_v1.current_event_summary, "
        "published_v1.current_event_detail, published_v1.title_search, "
        "published_v1.distribution_candidates, published_v1.fulltext_export "
        "TO srbg_projection_reader"
    )
    op.execute("GRANT USAGE ON SCHEMA published_v1 TO srbg_publication_writer, srbg_admin_role")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA published_v1 "
        "TO srbg_publication_writer"
    )
    op.execute(
        "REVOKE ALL ON public.event_identity_binding, "
        "public.projection_reconciliation_difference, public.audit_chain_anchor FROM PUBLIC"
    )
    op.execute(
        "GRANT SELECT, INSERT ON public.event_identity_binding, "
        "public.projection_reconciliation_difference, public.audit_chain_anchor "
        "TO srbg_publication_writer"
    )
    op.execute("GRANT INSERT ON public.event TO srbg_publication_writer")


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON ALL TABLES IN SCHEMA published_v1 FROM srbg_projection_reader, srbg_publication_writer"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS append_audit_event(uuid,text,uuid,text,uuid,jsonb,jsonb,text,text,timestamptz)"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_sync_publication_risk_tier ON intelligence_item")
    op.execute("DROP FUNCTION IF EXISTS sync_publication_risk_tier()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_invalidate_event_projection_on_publication_change "
        "ON publication"
    )
    op.execute("DROP FUNCTION IF EXISTS invalidate_event_projection_on_publication_change()")
    op.drop_table("projection_reconciliation_difference")
    op.drop_table("audit_chain_anchor")
    op.drop_table("event_identity_binding")
    op.execute("DROP SCHEMA published_v1 CASCADE")
    op.drop_constraint("ck_item_r4_no_projection", "intelligence_item", type_="check")
    op.drop_constraint("ck_item_projection_level", "intelligence_item", type_="check")
    op.drop_constraint("ck_item_content_severity", "intelligence_item", type_="check")
    op.drop_constraint("ck_item_legacy_risk_compatibility", "intelligence_item", type_="check")
    op.drop_constraint("ck_item_publication_risk_tier", "intelligence_item", type_="check")
    op.drop_column("intelligence_item", "projection_level")
    op.drop_column("intelligence_item", "content_severity")
    op.drop_column("intelligence_item", "publication_risk_tier")
    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
