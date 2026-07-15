"""Versioned, idempotent and resumable Item-to-Event shadow backfill."""

# ruff: noqa: E501,S608 -- SQL is inline and table names come from a closed local tuple.

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from srbg_api.event_unification.domain import EVENT_TYPE_BY_ITEM_TYPE
from srbg_api.identifiers import uuid7

TASK_VERSION = "round14-event-unification-v1"
SYSTEM_ACTOR = UUID("019b0000-0000-7000-8000-000000001400")


@dataclass(frozen=True, slots=True)
class EventMigrationReport:
    run_id: UUID
    migrated: int
    reused: int
    blocked: int
    consumer_differences: int


async def backfill_event_unification(
    engine: Any, *, actor_id: UUID = SYSTEM_ACTOR, chunk_size: int = 500
) -> EventMigrationReport:
    """Run bounded transactions until the durable checkpoint reaches EOF."""

    if not 1 <= chunk_size <= 5000:
        raise ValueError("chunk_size must be between 1 and 5000")
    run_id = await _start_or_resume(engine)
    migrated = reused = blocked = 0
    while True:
        async with engine.begin() as connection:
            checkpoint = await connection.scalar(
                text(
                    "SELECT last_item_id FROM event_migration_checkpoint WHERE run_id=:run_id AND consumer='IDENTITY' FOR UPDATE"
                ),
                {"run_id": run_id},
            )
            rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT item.id, item.item_type, item.title, item.primary_document_id,
                                   binding.event_id, lineage.role AS source_role
                              FROM intelligence_item item
                              JOIN publication pub ON pub.item_id=item.id AND pub.status='PUBLISHED'
                              LEFT JOIN event_identity_binding binding ON binding.item_id=item.id
                              LEFT JOIN source_lineage lineage ON lineage.item_id=item.id
                             WHERE (CAST(:after_id AS uuid) IS NULL
                                    OR item.id > CAST(:after_id AS uuid))
                             ORDER BY item.id LIMIT :row_limit
                            """
                        ),
                        {"after_id": checkpoint, "row_limit": chunk_size},
                    )
                ).mappings()
            )
            if not rows:
                break
            for row in rows:
                outcome = await _migrate_item(connection, run_id, row, actor_id)
                if outcome == "MIGRATED":
                    migrated += 1
                elif outcome == "REUSED":
                    reused += 1
                else:
                    blocked += 1
            await connection.execute(
                text(
                    "UPDATE event_migration_checkpoint SET last_item_id=:last_id, processed_count=processed_count+:count, updated_at=:now WHERE run_id=:run_id AND consumer='IDENTITY'"
                ),
                {
                    "last_id": rows[-1]["id"],
                    "count": len(rows),
                    "now": datetime.now(UTC),
                    "run_id": run_id,
                },
            )
    differences = await _shadow_consumers_and_reconcile(engine, run_id, chunk_size)
    async with engine.begin() as connection:
        blocked = int(
            await connection.scalar(
                text("SELECT count(*) FROM event_migration_blocker WHERE run_id=:run_id"),
                {"run_id": run_id},
            )
            or 0
        )
        await connection.execute(
            text(
                "UPDATE event_migration_run SET status=:status, completed_at=:now WHERE id=:run_id"
            ),
            {
                "status": "SUCCEEDED" if differences == 0 and blocked == 0 else "NEEDS_REVIEW",
                "now": datetime.now(UTC),
                "run_id": run_id,
            },
        )
    return EventMigrationReport(run_id, migrated, reused, blocked, differences)


async def _start_or_resume(engine: Any) -> UUID:
    async with engine.begin() as connection:
        existing = await connection.scalar(
            text("SELECT id FROM event_migration_run WHERE task_version=:version"),
            {"version": TASK_VERSION},
        )
        run_id = UUID(str(existing)) if existing else uuid7()
        now = datetime.now(UTC)
        await connection.execute(
            text(
                "INSERT INTO event_migration_run (id,task_version,status,auto_merge,started_at) VALUES (:id,:version,'RUNNING',false,:now) ON CONFLICT (task_version) DO UPDATE SET status='RUNNING', completed_at=NULL"
            ),
            {"id": run_id, "version": TASK_VERSION, "now": now},
        )
        await connection.execute(
            text(
                "INSERT INTO event_migration_checkpoint (run_id,consumer,last_item_id,processed_count,updated_at) VALUES (:run_id,'IDENTITY',NULL,0,:now) ON CONFLICT (run_id,consumer) DO NOTHING"
            ),
            {"run_id": run_id, "now": now},
        )
        return run_id


async def _migrate_item(connection: Any, run_id: UUID, row: Any, actor_id: UUID) -> str:
    item_id = row["id"]
    if row["event_id"] is not None:
        event_id = row["event_id"]
        outcome = "REUSED"
    else:
        event_type = EVENT_TYPE_BY_ITEM_TYPE.get(str(row["item_type"]))
        if event_type is None:
            await _block(
                connection,
                run_id,
                item_id,
                "UNCLASSIFIED_ITEM_TYPE",
                {"item_type": str(row["item_type"])},
            )
            return "BLOCKED"
        confirmed = list(
            (
                await connection.execute(
                    text(
                        "SELECT event_id FROM event_item WHERE item_id=:item_id ORDER BY confirmed_at,event_id LIMIT 2"
                    ),
                    {"item_id": item_id},
                )
            ).scalars()
        )
        if len(confirmed) > 1:
            await _block(
                connection,
                run_id,
                item_id,
                "MULTIPLE_CONFIRMED_EVENTS",
                {"event_ids": [str(value) for value in confirmed]},
            )
            return "BLOCKED"
        event_id = confirmed[0] if confirmed else uuid7()
        now = datetime.now(UTC)
        if not confirmed:
            await connection.execute(
                text(
                    "INSERT INTO event (id,event_type,title,subject_names,confirmation_status,confirmed_by,confirmed_at,created_at,updated_at) VALUES (:id,:event_type,:title,'[]'::jsonb,'CONFIRMED',:actor,:now,:now,:now)"
                ),
                {
                    "id": event_id,
                    "event_type": event_type,
                    "title": row["title"],
                    "actor": actor_id,
                    "now": now,
                },
            )
        await connection.execute(
            text(
                "INSERT INTO event_identity_binding (event_id,item_id,binding_kind,created_by,created_at,rule_version) VALUES (:event_id,:item_id,:kind,:actor,:now,:version) ON CONFLICT (item_id) DO NOTHING"
            ),
            {
                "event_id": event_id,
                "item_id": item_id,
                "kind": "CONFIRMED_MEMBERSHIP" if confirmed else "ROUND14_ONE_TO_ONE",
                "actor": actor_id,
                "now": now,
                "version": TASK_VERSION,
            },
        )
        outcome = "MIGRATED"
    await connection.execute(
        text(
            "INSERT INTO document_event_membership (id,document_id,event_id,source_role,decided_by,created_at) VALUES (:id,:document_id,:event_id,:role,:actor,:now) ON CONFLICT (document_id,event_id) DO NOTHING"
        ),
        {
            "id": uuid7(),
            "document_id": row["primary_document_id"],
            "event_id": event_id,
            "role": row["source_role"],
            "actor": actor_id,
            "now": datetime.now(UTC),
        },
    )
    if row["source_role"] is None:
        await _block(connection, run_id, item_id, "SOURCE_ROLE_REQUIRES_REVIEW", {})
    return outcome


async def _block(
    connection: Any, run_id: UUID, item_id: UUID, code: str, details: dict[str, Any]
) -> None:
    await connection.execute(
        text(
            "INSERT INTO event_migration_blocker (run_id,item_id,reason_code,details,created_at) VALUES (:run_id,:item_id,:code,CAST(:details AS jsonb),:now) ON CONFLICT (run_id,item_id) DO UPDATE SET reason_code=EXCLUDED.reason_code, details=EXCLUDED.details"
        ),
        {
            "run_id": run_id,
            "item_id": item_id,
            "code": code,
            "details": json.dumps(details, sort_keys=True),
            "now": datetime.now(UTC),
        },
    )


async def _shadow_consumers_and_reconcile(engine: Any, run_id: UUID, chunk_size: int) -> int:
    del (
        chunk_size
    )  # identity chunks bound the facts; these indexed updates are finite and idempotent.
    async with engine.begin() as connection:
        for table in (
            "search_projection",
            "daily_report_item",
            "saved_item",
            "collection_item",
            "item_feedback",
        ):
            await connection.execute(
                text(
                    f"UPDATE {table} consumer SET event_id=binding.event_id FROM event_identity_binding binding WHERE consumer.item_id=binding.item_id AND consumer.event_id IS NULL"
                )
            )
            missing = int(
                await connection.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE event_id IS NULL")
                )
                or 0
            )
            if missing:
                await connection.execute(
                    text(
                        "INSERT INTO event_consumer_parity_difference (id,run_id,consumer,difference_code,details,detected_at) VALUES (:id,:run_id,:consumer,'MISSING_EVENT_ID',jsonb_build_object('count',:count),:now)"
                    ),
                    {
                        "id": uuid7(),
                        "run_id": run_id,
                        "consumer": table,
                        "count": missing,
                        "now": datetime.now(UTC),
                    },
                )
        await connection.execute(
            text(
                "INSERT INTO topic_event (topic_id,event_id,created_at) SELECT topic_id,event_id,confirmed_at FROM topic_cluster_event ON CONFLICT DO NOTHING"
            )
        )
        return int(
            await connection.scalar(
                text("SELECT count(*) FROM event_consumer_parity_difference WHERE run_id=:run_id"),
                {"run_id": run_id},
            )
            or 0
        )
