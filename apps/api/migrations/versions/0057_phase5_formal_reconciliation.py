"""Reconcile the formal Crossref sibling with the Phase 3/4 authority line.

Revision ID: 0057_phase5_formal_reconciliation
Revises: 0056_phase4_controlled_handoff, 0055_crossref_metadata_admission
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0057_phase5_formal_reconciliation"
down_revision = (
    "0056_phase4_controlled_handoff",
    "0055_crossref_metadata_admission",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "stream_config_version"
_COLUMN = "admission_research_id"
_FOREIGN_KEY = "fk_stream_config_admission_research"
_CHECK = "ck_stream_config_exactly_one_provenance"
_INDEX = "ix_stream_config_admission_research"


def _constraint_definition(bind: sa.Connection, name: str) -> str | None:
    value = bind.execute(
        sa.text(
            "SELECT pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE conname=:name"
        ),
        {"name": name},
    ).scalar_one_or_none()
    return None if value is None else str(value)


def _index_exists(bind: sa.Connection, name: str) -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM pg_indexes "
                "WHERE schemaname=current_schema() AND indexname=:name)"
            ),
            {"name": name},
        ).scalar_one()
    )


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]: column for column in sa.inspect(bind).get_columns(_TABLE)
    }

    if _COLUMN not in columns:
        op.add_column(
            _TABLE,
            sa.Column(_COLUMN, postgresql.UUID(as_uuid=True), nullable=True),
        )
    else:
        column_type = str(columns[_COLUMN]["type"]).upper()
        if column_type != "UUID":
            raise RuntimeError("0057_CROSSREF_PROVENANCE_TYPE_MISMATCH")

    probe = columns.get("probe_run_id")
    if probe is None:
        raise RuntimeError("0057_PROBE_PROVENANCE_COLUMN_MISSING")
    if not bool(probe["nullable"]):
        op.alter_column(_TABLE, "probe_run_id", nullable=True)

    foreign_key = _constraint_definition(bind, _FOREIGN_KEY)
    if foreign_key is None:
        op.create_foreign_key(
            _FOREIGN_KEY,
            _TABLE,
            "source_research_disposition_v2",
            [_COLUMN],
            ["id"],
            ondelete="RESTRICT",
        )
    elif "source_research_disposition_v2" not in foreign_key:
        raise RuntimeError("0057_CROSSREF_PROVENANCE_FK_MISMATCH")

    provenance_check = _constraint_definition(bind, _CHECK)
    if provenance_check is None:
        op.create_check_constraint(
            _CHECK,
            _TABLE,
            "(probe_run_id IS NULL) <> (admission_research_id IS NULL)",
        )
    elif "probe_run_id" not in provenance_check or _COLUMN not in provenance_check:
        raise RuntimeError("0057_CROSSREF_PROVENANCE_CHECK_MISMATCH")

    if not _index_exists(bind, _INDEX):
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    durable = bool(
        bind.execute(
            sa.text(
                "SELECT EXISTS(SELECT 1 FROM stream_config_version "
                "WHERE admission_research_id IS NOT NULL)"
            )
        ).scalar_one()
    )
    if durable:
        raise RuntimeError("0057_FORMAL_RECONCILIATION_DOWNGRADE_BLOCKED")

    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_constraint(_FOREIGN_KEY, _TABLE, type_="foreignkey")
    op.drop_column(_TABLE, _COLUMN)
    op.alter_column(_TABLE, "probe_run_id", nullable=False)
