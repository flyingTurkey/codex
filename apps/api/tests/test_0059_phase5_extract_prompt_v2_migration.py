from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.config import Config
from alembic.script import ScriptDirectory
from srbg_api.ai_pipeline.content_preparation import (
    EXTRACTION_PROMPT_VERSION,
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_TASK_PROMPT_TEMPLATE,
)

MIGRATION = Path("apps/api/migrations/versions/0059_phase5_extract_prompt_v2.py")


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("phase5_extract_prompt_v2", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_phase5_extract_prompt_v2_is_the_single_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_heads() == ["0059_phase5_extract_prompt_v2"]


def test_registered_prompt_identity_matches_the_runtime_template() -> None:
    migration = _migration_module()

    assert migration.PROMPT_VERSION == EXTRACTION_PROMPT_VERSION
    assert migration.SYSTEM_PROMPT == EXTRACTION_SYSTEM_PROMPT
    assert migration.TASK_PROMPT == EXTRACTION_TASK_PROMPT_TEMPLATE


def test_prompt_downgrade_is_blocked_after_durable_use() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision = "0058_phase5_technical_exception_acl"' in source
    assert "0059_DOWNGRADE_BLOCKED: extraction prompt has durable uses" in source
    assert "JOIN ai_prompt_version prompt ON prompt.id=step.prompt_version_id" in source
