"""Allow an explicit, audited Owner override to authorize auto-pass.

Revision ID: 0047_owner_gold_override_go
Revises: 0046_owner_gold_prediction_seal
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0047_owner_gold_override_go"
down_revision = "0046_owner_gold_prediction_seal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE owner_gold_calibration_v2 "
        "DROP CONSTRAINT ck_owner_gold_calibration_fail_closed_v2"
    )
    op.execute(
        "ALTER TABLE owner_gold_calibration_v2 ADD CONSTRAINT "
        "ck_owner_gold_calibration_fail_closed_v2 CHECK ("
        "(decision='GO' AND authorizes_auto_pass=true "
        "AND auto_pass_threshold_bps BETWEEN 0 AND 10000 AND ("
        "(precision_bps>=9000 AND recall_bps>=9000 AND locked_negative_leaks=0) "
        "OR reasons ? 'OWNER_OVERRIDE_GO')) OR "
        "(decision='NO_GO' AND authorizes_auto_pass=false "
        "AND auto_pass_threshold_bps IS NULL))"
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_override = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM owner_gold_calibration_v2 "
            "WHERE decision='GO' AND reasons ? 'OWNER_OVERRIDE_GO')"
        )
    ).scalar_one()
    if has_override:
        raise RuntimeError("OWNER_GOLD_OVERRIDE_DOWNGRADE_BLOCKED")
    op.execute(
        "ALTER TABLE owner_gold_calibration_v2 "
        "DROP CONSTRAINT ck_owner_gold_calibration_fail_closed_v2"
    )
    op.execute(
        "ALTER TABLE owner_gold_calibration_v2 ADD CONSTRAINT "
        "ck_owner_gold_calibration_fail_closed_v2 CHECK ("
        "(decision='GO' AND authorizes_auto_pass=true "
        "AND auto_pass_threshold_bps BETWEEN 0 AND 10000 "
        "AND precision_bps>=9000 AND recall_bps>=9000 "
        "AND locked_negative_leaks=0) OR "
        "(decision='NO_GO' AND authorizes_auto_pass=false "
        "AND auto_pass_threshold_bps IS NULL))"
    )
