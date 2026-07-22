"""Make source-content handoff state ordering deterministic.

Revision ID: 0050_autonomous_handoff_state_order
Revises: 0049_autonomous_content_switch
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0050_autonomous_handoff_state_order"
down_revision = "0049_autonomous_content_switch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_STATE_ORDER = "state.created_at DESC,state.id DESC"
STATE_ORDER = (
    "state.created_at DESC,CASE state.state "
    "WHEN 'FAILED' THEN 90 WHEN 'QUARANTINED' THEN 90 "
    "WHEN 'READY' THEN 80 WHEN 'OCR_COMPLETE' THEN 70 "
    "WHEN 'SECURITY_PASSED' THEN 60 WHEN 'OCR_PENDING' THEN 50 "
    "WHEN 'PARSING' THEN 40 WHEN 'RECEIVED' THEN 30 ELSE 0 END DESC,state.id DESC"
)


def _replace_state_order(*, source: str, target: str) -> None:
    connection = op.get_bind()
    definition = connection.execute(
        sa.text(
            "SELECT pg_get_functiondef("
            "'handoff_source_content_to_ai(uuid,uuid,timestamptz)'::regprocedure)"
        )
    ).scalar_one()
    if source not in definition:
        raise RuntimeError("AUTONOMOUS_HANDOFF_STATE_ORDER_DEFINITION_UNEXPECTED")
    connection.execute(sa.text(definition.replace(source, target)))


def upgrade() -> None:
    _replace_state_order(source=LEGACY_STATE_ORDER, target=STATE_ORDER)


def downgrade() -> None:
    _replace_state_order(source=STATE_ORDER, target=LEGACY_STATE_ORDER)
