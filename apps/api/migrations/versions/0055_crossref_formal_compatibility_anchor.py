"""Recognize the historical formal Crossref sibling without replaying it.

Revision ID: 0055_crossref_metadata_admission
Revises: 0054_policy_optimization

The Phase 2C migration was applied to the formal database on its own branch.
Its executable connector implementation is not part of the Phase 5 authority
line.  This anchor only makes that immutable, already-applied revision visible
to Alembic.  Revision 0057 owns the forward schema reconciliation for both
paths; this file deliberately contains no copied Phase 2C DDL or seed data.
"""

from __future__ import annotations

from collections.abc import Sequence

revision = "0055_crossref_metadata_admission"
down_revision = "0054_policy_optimization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Leave fresh installs for the 0057 reconciliation to normalize."""


def downgrade() -> None:
    """The compatibility anchor has no independent schema effects."""
