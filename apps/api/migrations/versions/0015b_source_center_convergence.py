"""Converge previously applied Round 15 development schemas without data loss.

Revision ID: 0015b_source_center_convergence
Revises: 0015_source_center_v2

This forward-only convergence step repairs databases that applied the Round 15
revision before its fixture replay, structured-document and policy URL
boundaries were complete.  It never deletes governance facts.  Downgrading one
step intentionally keeps the converged 0015 schema; the 0015 downgrade remains
the sole guarded rollback to Round 14.
"""

# ruff: noqa: E501 -- static migration DDL remains auditable inline.

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from types import ModuleType

import sqlalchemy as sa
from alembic import op

revision: str = "0015b_source_center_convergence"
down_revision: str | Sequence[str] | None = "0015_source_center_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _round15() -> ModuleType:
    return import_module("apps.api.migrations.versions.0015_source_center_v2")


def upgrade() -> None:
    round15 = _round15()
    _ensure_fixture_replay_result_table()
    round15._expand_fixture_document_kinds()

    # Replace every source write boundary as one coherent contract so an
    # already-applied database cannot retain an older policy/trial function.
    round15._drop_source_write_boundaries()
    round15._create_attachment_attempt_boundary()
    round15._create_raw_security_boundaries()
    round15._create_document_version_execution_domain_boundary()
    round15._create_source_command_boundary()
    round15._configure_source_roles()
    _verify_converged_schema()


def _ensure_fixture_replay_result_table() -> None:
    if sa.inspect(op.get_bind()).has_table("source_fixture_replay_result"):
        return
    op.create_table(
        "source_fixture_replay_result",
        sa.Column("trial_run_id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("connector_config_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("raw_capture_count", sa.Integer(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("transport_call_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trial_run_id", "source_id"],
            ["source_trial_run.id", "source_trial_run.source_id"],
            name="fk_fixture_replay_trial_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["connector_config_version_id", "source_id"],
            ["connector_config_version.id", "connector_config_version.source_id"],
            name="fk_fixture_replay_config_source",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PASSED','FAILED')", name="ck_fixture_replay_status"
        ),
        sa.CheckConstraint(
            "reason_code ~ '^[A-Z0-9_]{1,100}$'",
            name="ck_fixture_replay_reason_code",
        ),
        sa.CheckConstraint(
            "raw_capture_count >= 0 AND document_count >= 0 "
            "AND transport_call_count >= 0",
            name="ck_fixture_replay_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'PASSED' OR (raw_capture_count > 0 AND document_count > 0)",
            name="ck_fixture_replay_passed_has_output",
        ),
    )


def _verify_converged_schema() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('source_fixture_replay_result') IS NULL
             OR NOT EXISTS (
                  SELECT 1 FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='document'
                     AND column_name='document_kind'
                     AND character_maximum_length=30
                )
             OR to_regprocedure(
                  'record_source_fixture_replay_result(uuid,uuid,uuid,text,text,integer,integer,integer,uuid,timestamp with time zone)'
                ) IS NULL
             OR to_regprocedure('source_trial_quality_summary(uuid)') IS NULL
             OR to_regprocedure(
                  'complete_source_trial_run_with_audit(uuid,text,jsonb,text,uuid,text,text,uuid,timestamp with time zone)'
                ) IS NULL
             OR to_regprocedure('enforce_document_version_execution_domain()') IS NULL
             OR has_column_privilege(
                  'srbg_runtime','connector_config_version','credential_ref','SELECT'
                )
             OR has_column_privilege(
                  'srbg_worker_role','connector_config_version','credential_ref','SELECT'
                )
             OR has_column_privilege(
                  'srbg_publication_writer','connector_config_version','credential_ref','SELECT'
                ) THEN
            RAISE EXCEPTION '0015_SOURCE_SCHEMA_CONVERGENCE_BLOCKED';
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    # No destructive action here: 0015 now defines this converged shape.  A
    # subsequent downgrade of 0015 invokes its governance-fact guard before
    # returning to Round 14.
    pass
