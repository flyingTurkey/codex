"""Register and authorize the autonomous content qualification production seam.

Revision ID: 0049_autonomous_content_switch
Revises: 0048_autonomous_policy_foundation
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from srbg_api.intelligence_v2.autonomous_policy import (
    CLASSIFICATION_TASK_PROMPT_TEMPLATE,
    PRODUCTION_CLASSIFICATION_SYSTEM_PROMPT,
)

revision = "0049_autonomous_content_switch"
down_revision = "0048_autonomous_policy_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROMPT_VERSION = "autonomous-classify-2.7.0"
SCHEMA_VERSION = "autonomous-classify-output-2.0.0"
SYSTEM_PROMPT = PRODUCTION_CLASSIFICATION_SYSTEM_PROMPT
TASK_PROMPT = CLASSIFICATION_TASK_PROMPT_TEMPLATE


def upgrade() -> None:
    _expand_primary_type_storage_constraints()
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "docs"
        / "codex-kit"
        / "assets"
        / "schemas"
        / "autonomous-classify-output.schema.json"
    )
    schema_json = json.dumps(
        json.loads(schema_path.read_text(encoding="utf-8")),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    prompt_hash = sha256(f"{SYSTEM_PROMPT}\n{TASK_PROMPT}".encode()).hexdigest()
    schema_hash = sha256(schema_json.encode()).hexdigest()
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO ai_prompt_version(id,step,version,system_prompt,task_prompt,"
            "prompt_sha256,created_by,created_at) VALUES(CAST(:id AS uuid),'CLASSIFY',"
            ":version,:system,:task,:hash,CAST(:actor AS uuid),now()) "
            "ON CONFLICT(step,version) DO NOTHING"
        ).bindparams(
            id="01a00000-0000-7000-8000-000000000101",
            version=PROMPT_VERSION,
            system=SYSTEM_PROMPT,
            task=TASK_PROMPT,
            hash=prompt_hash,
            actor="019b0000-0000-7000-8000-000000009002",
        )
    )
    registered_prompt_hash = connection.scalar(
        sa.text(
            "SELECT prompt_sha256 FROM ai_prompt_version WHERE step='CLASSIFY' AND version=:version"
        ).bindparams(version=PROMPT_VERSION)
    )
    if registered_prompt_hash != prompt_hash:
        raise RuntimeError("PROMPT_REGISTRY_IDENTITY_MISMATCH")
    connection.execute(
        sa.text(
            "INSERT INTO ai_schema_version(id,step,version,schema_document,schema_sha256,"
            "created_at) VALUES(CAST(:id AS uuid),'CLASSIFY',:version,CAST(:schema AS jsonb),"
            ":hash,now()) ON CONFLICT(step,version) DO NOTHING"
        ).bindparams(
            id="01a00000-0000-7000-8000-000000000102",
            version=SCHEMA_VERSION,
            schema=schema_json,
            hash=schema_hash,
        )
    )
    registered_schema_hash = connection.scalar(
        sa.text(
            "SELECT schema_sha256 FROM ai_schema_version WHERE step='CLASSIFY' AND version=:version"
        ).bindparams(version=SCHEMA_VERSION)
    )
    if registered_schema_hash != schema_hash:
        raise RuntimeError("SCHEMA_REGISTRY_IDENTITY_MISMATCH")
    op.execute(
        "GRANT SELECT,INSERT ON qualification_policy_bundle_v2,"
        "automated_qualification_decision_v2,qualification_policy_evaluation_v2,"
        "qualification_shadow_decision_v2 TO srbg_worker_role"
    )


def _expand_primary_type_storage_constraints() -> None:
    op.drop_constraint("ck_round07_item_type", "intelligence_item", type_="check")
    op.drop_constraint("ck_round05_item_channel", "intelligence_item", type_="check")
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_t41_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','INDUSTRY_UPDATE','JOURNAL_PAPER',"
        "'SOFTWARE_PRODUCT','IOT_PRODUCT','LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT',"
        "'SAFETY_REGULATION','SAFETY_CASE')",
    )
    op.create_check_constraint(
        "ck_t41_item_channel",
        "intelligence_item",
        "channel IN ('DIGITAL','SAFETY','INDUSTRY')",
    )
    op.create_check_constraint(
        "ck_t41_event_type",
        "event",
        "event_type IN ('SAFETY_INCIDENT','REGULATION_CHANGE','DIGITAL_PROJECT',"
        "'RESEARCH_RESULT','PRODUCT_RELEASE','INDUSTRY_UPDATE')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM automated_qualification_decision_v2 decision "
            "JOIN qualification_policy_bundle_v2 bundle ON bundle.id=decision.policy_bundle_id "
            "WHERE bundle.prompt_version=:prompt OR bundle.schema_version=:schema "
            "UNION ALL SELECT 1 FROM qualification_shadow_decision_v2 decision "
            "JOIN qualification_policy_bundle_v2 bundle ON bundle.id=decision.policy_bundle_id "
            "WHERE bundle.prompt_version=:prompt OR bundle.schema_version=:schema)"
        ),
        {"prompt": PROMPT_VERSION, "schema": SCHEMA_VERSION},
    ).scalar_one()
    if used:
        raise RuntimeError("AUTONOMOUS_CONTENT_SWITCH_DOWNGRADE_BLOCKED")
    _restore_legacy_storage_constraints()
    op.execute(
        "REVOKE INSERT ON qualification_policy_bundle_v2 FROM srbg_worker_role"
    )
    op.execute(
        "REVOKE SELECT,INSERT ON "
        "automated_qualification_decision_v2,qualification_policy_evaluation_v2,"
        "qualification_shadow_decision_v2 FROM srbg_worker_role"
    )
    op.execute("ALTER TABLE ai_prompt_version DISABLE TRIGGER USER")
    op.execute(
        sa.text(
            "DELETE FROM ai_prompt_version WHERE step='CLASSIFY' AND version=:version"
        ).bindparams(version=PROMPT_VERSION)
    )
    op.execute("ALTER TABLE ai_prompt_version ENABLE TRIGGER USER")
    op.execute("ALTER TABLE ai_schema_version DISABLE TRIGGER USER")
    op.execute(
        sa.text(
            "DELETE FROM ai_schema_version WHERE step='CLASSIFY' AND version=:version"
        ).bindparams(version=SCHEMA_VERSION)
    )
    op.execute("ALTER TABLE ai_schema_version ENABLE TRIGGER USER")


def _restore_legacy_storage_constraints() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM intelligence_item "
            "WHERE item_type='INDUSTRY_UPDATE' OR channel='INDUSTRY')"
        )
    ).scalar_one():
        raise RuntimeError("AUTONOMOUS_CONTENT_SWITCH_DOWNGRADE_BLOCKED")
    op.drop_constraint("ck_t41_item_type", "intelligence_item", type_="check")
    op.drop_constraint("ck_t41_item_channel", "intelligence_item", type_="check")
    op.drop_constraint("ck_t41_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_round07_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','JOURNAL_PAPER','SOFTWARE_PRODUCT','IOT_PRODUCT',"
        "'LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT','SAFETY_REGULATION','SAFETY_CASE')",
    )
    op.create_check_constraint(
        "ck_round05_item_channel",
        "intelligence_item",
        "channel IN ('DIGITAL','SAFETY')",
    )
    op.create_check_constraint(
        "ck_event_type",
        "event",
        "event_type IN ('SAFETY_INCIDENT','REGULATION_CHANGE','DIGITAL_PROJECT',"
        "'RESEARCH_RESULT','PRODUCT_RELEASE')",
    )
