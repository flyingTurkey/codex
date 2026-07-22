# ruff: noqa: RUF001
import os
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.ai_pipeline.content_preparation import (
    PreparationDocument,
    production_policy_for,
)
from srbg_api.ai_pipeline.preparation import DocumentBlock
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import (
    AdjudicationInput,
    AutomatedAdjudicationService,
)
from srbg_worker.ai_content_preparation import PostgresAiPreparationRepository

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        "SRBG_TEST_ADMIN_DATABASE_URL" not in os.environ,
        reason="isolated integration database is required",
    ),
]


class ModelMustNotRun:
    def classify(
        self, *, system_prompt: str, document_text: str, semantic_recheck: bool
    ) -> dict[str, object]:
        raise AssertionError("locked negative must filter before model dispatch")


async def test_filtered_decision_is_idempotent_and_has_no_reader_materialization() -> None:
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    worker = create_async_engine(os.environ["SRBG_WORKER_DATABASE_URL"])
    raw_id = uuid7()
    document_id = uuid7()
    version_id = uuid7()
    unique = sha256(str(version_id).encode()).hexdigest()
    now = datetime.now(UTC)
    try:
        async with admin.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            assert source_id is not None
            await connection.execute(
                text(
                    "INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,scan_status,created_at) VALUES(:id,:hash,:key,1,'text/html',"
                    "'text/html','CLEAN',:now)"
                ),
                {"id": raw_id, "hash": unique, "key": f"t41/{unique}", "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO document(id,source_id,canonical_url,document_kind,"
                    "first_discovered_at) VALUES(:id,:source,:url,'HTML',:now)"
                ),
                {
                    "id": document_id,
                    "source": source_id,
                    "url": f"https://example.invalid/t41/{version_id}",
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version(id,document_id,raw_object_id,version_number,"
                    "content_hash,original_filename,acquired_at) VALUES("
                    ":id,:document,:raw,1,:hash,'fixture.html',:now)"
                ),
                {
                    "id": version_id,
                    "document": document_id,
                    "raw": raw_id,
                    "hash": unique,
                    "now": now,
                },
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version WHERE id=:document"),
                {"version": version_id, "document": document_id},
            )
        preparation = PreparationDocument(
            run_id=uuid7(),
            document_version_id=version_id,
            raw_object_id=raw_id,
            source_stream_policy_version="integration-stream-policy-1",
            source_code="T41-INTEGRATION",
            canonical_url=f"https://example.invalid/t41/{version_id}",
            title="旅游消费促销",
            source_name="integration",
            blocks=(
                DocumentBlock(
                    block_id="block-1",
                    page_number=1,
                    text="旅游消费促销活动，与工程无关。",
                    locator_value="html:p:1",
                ),
            ),
        )
        policy = production_policy_for(preparation)
        trace = AutomatedAdjudicationService(
            policy=policy,
            model_edge=ModelMustNotRun(),
            clock=lambda: now,
            id_factory=uuid7,
        ).adjudicate(
            AdjudicationInput(
                document_version_id=version_id,
                raw_object_id=raw_id,
                normalized_input_sha256=unique,
                document_text="旅游消费促销活动，与工程无关。",
                allowed_evidence_locators=frozenset({"block-1"}),
            )
        )
        repository = PostgresAiPreparationRepository(
            engine=worker,
            object_store=cast(Any, object()),
            parser=cast(Any, object()),
            environment="acceptance",
            max_document_bytes=1,
        )
        await repository.append_automated_decision(trace, policy)
        await repository.append_automated_decision(trace, policy)
        async with admin.connect() as connection:
            decision_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM automated_qualification_decision_v2 "
                    "WHERE document_version_id=:version AND disposition='AUTO_FILTERED'"
                ),
                {"version": version_id},
            )
            item_count = await connection.scalar(
                text("SELECT count(*) FROM intelligence_item WHERE primary_document_id=:document"),
                {"document": document_id},
            )
            review_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM owner_review_case_v2 "
                    "WHERE document_version_id=:version"
                ),
                {"version": version_id},
            )
        assert decision_count == 1
        assert item_count == 0
        assert review_count == 0
    finally:
        await admin.dispose()
        await worker.dispose()
