"""Repair the least-privilege API read used by technical retry projection.

Revision ID: 0058_phase5_technical_exception_acl
Revises: 0057_phase5_formal_reconciliation
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "0058_phase5_technical_exception_acl"
down_revision = "0057_phase5_formal_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON ai_compensation_run_v2 TO srbg_api_role")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON ai_compensation_run_v2 FROM srbg_api_role")
