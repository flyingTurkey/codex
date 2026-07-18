"""Allow the internal worker to read controlled-run stop authority.

Revision ID: 0032_controlled_run_worker_read
Revises: 0031_controlled_personal_runs
"""

from collections.abc import Sequence

from alembic import op

revision = "0032_controlled_run_worker_read"
down_revision = "0031_controlled_personal_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON personal_controlled_run TO srbg_worker_role")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON personal_controlled_run FROM srbg_worker_role")
