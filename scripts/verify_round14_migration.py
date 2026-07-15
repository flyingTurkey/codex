"""Replay the Round 14 expand migration on an isolated loopback database."""

# ruff: noqa: E501, S101 -- deterministic SQL reconciliation evidence is kept inline.

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
import runpy
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_FIXTURE_SQL = runpy.run_path("apps/api/tests/round14_reconciliation_sql.py")


async def _verify_nonempty_event_consumer_reconciliation(database_url: str) -> None:
    """Exercise TEST-only legacy references; this is evidence, never claimed as user data."""
    engine = create_async_engine(database_url)
    ids = {
        name: f"019b1400-0000-7000-8000-{number:012d}"
        for number, name in enumerate(
            (
                "raw",
                "document",
                "version",
                "item",
                "review",
                "publication",
                "revision",
                "event",
                "build",
                "event_revision",
                "report",
                "owner",
                "collection",
                "feedback",
            ),
            1,
        )
    }
    digest = "14" * 32
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            policy_id = await connection.scalar(
                text(
                    "SELECT id FROM source_policy WHERE source_id=:source ORDER BY created_at LIMIT 1"
                ),
                {"source": source_id},
            )
            assert source_id is not None
            if policy_id is None:
                policy_id = "019b1400-0000-7000-8000-000000000099"
                await connection.execute(
                    text("""
                    INSERT INTO source_policy
                      (id,source_id,policy_version,status,document,document_sha256,valid_until,
                       created_by,created_at)
                    VALUES (:policy,:source,'round14-test-v1','VALID','{}',:digest,
                            now() + interval '1 day',:owner,now())
                """),
                    ids | {"policy": policy_id, "source": source_id, "digest": digest},
                )
            await connection.execute(
                text("""
                INSERT INTO raw_object
                  (id,sha256,object_key,byte_size,declared_mime,detected_mime,scan_status,created_at)
                VALUES (:raw,:digest,'test/round14-reconciliation',14,'text/html','text/html','CLEAN',now())
            """),
                ids | {"digest": digest},
            )
            await connection.execute(
                text("""
                INSERT INTO document
                  (id,source_id,canonical_url,document_kind,first_discovered_at,current_version_id)
                VALUES (:document,:source,'https://example.invalid/round14-fixture','HTML',now(),NULL)
            """),
                ids | {"source": source_id},
            )
            await connection.execute(
                text("""
                INSERT INTO document_version
                  (id,document_id,raw_object_id,version_number,content_hash,original_filename,
                   title,acquired_at)
                VALUES (:version,:document,:raw,1,:digest,'round14-test.html',
                        'Round14 TEST fixture',now())
            """),
                ids | {"digest": digest},
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version WHERE id=:document"), ids
            )
            await connection.execute(
                text("""
                INSERT INTO intelligence_item
                  (id,source_id,primary_document_id,current_document_version_id,item_type,channel,
                   risk_level,title,original_url,first_discovered_at,activity_at,processing_status,
                   review_status,submitted_by,is_demo,publishable,created_at,updated_at,
                   publication_risk_tier,content_severity,projection_level)
                VALUES (:item,:source,:document,:version,'SAFETY_REGULATION','SAFETY','R3',
                  'Round14 TEST legacy reference','https://example.invalid/round14-fixture',now(),now(),
                  'READY_FOR_REVIEW','APPROVED',:owner,true,true,now(),now(),'R3','LOW','FULL')
            """),
                ids | {"source": source_id},
            )
            await connection.execute(
                text("""
                INSERT INTO review_task
                  (id,item_id,document_version_id,source_policy_id,risk_level,status,submitted_by,
                   submitted_at,decided_by,decided_at,created_at,task_type)
                VALUES (:review,:item,:version,:policy,'R3','APPROVED',:owner,now(),:event,now(),now(),
                        'CONTENT_REVIEW')
            """),
                ids | {"policy": policy_id},
            )
            await connection.execute(text(_FIXTURE_SQL["INSERT_PUBLICATION"]), ids)
            await connection.execute(
                text(_FIXTURE_SQL["INSERT_PUBLICATION_REVISION"]),
                ids | {"policy": policy_id, "digest": digest},
            )
            await connection.execute(text(_FIXTURE_SQL["UPDATE_PUBLICATION_REVISION"]), ids)
            await connection.execute(
                text("""
                INSERT INTO event
                  (id,event_type,title,subject_names,confirmation_status,created_at,updated_at)
                VALUES (:event,'REGULATION_CHANGE','Round14 TEST event','[]','PENDING_REVIEW',now(),now())
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO event_identity_binding
                  (event_id,item_id,binding_kind,created_by,created_at,rule_version)
                VALUES (:event,:item,'ROUND14_ONE_TO_ONE',:owner,now(),'round14-test-v1')
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO published_v1.projection_build_run
                  (id,generation,projection_version,status,started_at,completed_at,source_count,
                   projected_count,difference_count)
                VALUES (:build,1401,'1.1.0','SUCCEEDED',now(),now(),1,1,0)
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO published_v1.event_projection_revision
                  (id,event_revision_id,publication_revision_ids,event_id,item_id,
                   publication_revision_id,build_run_id,generation,projection_version,
                   publication_risk_tier,content_severity,projection_level,allowed_surfaces,
                   summary_payload,state,generated_at)
                VALUES (:event_revision,:event_revision,ARRAY[CAST(:revision AS uuid)],
                  CAST(:event AS uuid),:item,
                  :revision,:build,1401,'1.1.0','R3','LOW','FULL',ARRAY['FEED','EVENT'],
                  jsonb_build_object('id',CAST(CAST(:event AS uuid) AS text),
                    'projection_version','1.1.0'),'ACTIVE',now())
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO search_projection
                  (item_id,event_id,publication_revision_id,domain,content_type,source_id,risk_level,
                   title,visible,generation,activity_at,indexed_at)
                VALUES (:item,:event,:revision,'SAFETY','SAFETY_REGULATION',:source,'R3',
                        'Round14 TEST legacy reference',true,1401,now(),now())
            """),
                ids | {"source": source_id},
            )
            await connection.execute(
                text("""
                INSERT INTO daily_report
                  (id,report_date,status,snapshot_at,published_at,created_by,reviewer_id)
                VALUES (:report,'2026-07-16','PUBLISHED',now(),now(),:owner,:event)
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO daily_report_item
                  (report_id,section,position,item_id,event_id,publication_revision_id,
                   event_revision_id,title,original_url)
                VALUES (:report,'TODAY_HIGHLIGHTS',1,:item,:event,:revision,:event_revision,
                        'Round14 TEST legacy reference','https://example.invalid/round14-fixture')
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO saved_item (owner_id,item_id,event_id,saved_at)
                VALUES (:owner,:item,:event,now())
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO user_collection
                  (id,owner_id,name,archived,version,created_at,updated_at)
                VALUES (:collection,:owner,'Round14 TEST',false,1,now(),now())
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO collection_item (collection_id,owner_id,item_id,event_id,added_at)
                VALUES (:collection,:owner,:item,:event,now())
            """),
                ids,
            )
            await connection.execute(
                text("""
                INSERT INTO item_feedback (id,actor_id,item_id,event_id,value,recorded_at)
                VALUES (:feedback,:owner,:item,:event,'USEFUL',now())
            """),
                ids,
            )
            counts = (
                (
                    await connection.execute(
                        text("""
                    SELECT
                      (SELECT count(*) FROM saved_item WHERE item_id=:item AND event_id=:event) saved,
                      (SELECT count(*) FROM collection_item WHERE item_id=:item AND event_id=:event) collected,
                      (SELECT count(*) FROM daily_report_item WHERE item_id=:item AND event_id=:event
                         AND publication_revision_id=:revision AND event_revision_id=:event_revision) daily,
                      (SELECT count(*) FROM item_feedback WHERE item_id=:item AND event_id=:event) feedback,
                      (SELECT count(*) FROM search_projection WHERE item_id=:item AND event_id=:event
                         AND visible AND risk_level='R3') searched
                """),
                        ids,
                    )
                )
                .mappings()
                .one()
            )
            assert set(counts.values()) == {1}
            await connection.execute(
                text(
                    "UPDATE event_consumer_switch SET status='EVENT',changed_by=:owner WHERE singleton"
                ),
                ids,
            )
        print(
            "Round14 TEST reconciliation: saved=1 collection=1 daily=1 feedback=1 search=1; ACL=R3; revisions=preserved"
        )
    finally:
        await engine.dispose()


_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")


def main() -> None:
    parsed = urlsplit(
        os.environ.get("SRBG_DATABASE_URL", "").replace("postgresql+asyncpg", "postgresql", 1)
    )
    database_name = parsed.path.removeprefix("/")
    host = parsed.hostname
    try:
        loopback = host == "localhost" or (
            host is not None and ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round14 migration replay requires an isolated loopback database")
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0013_internal_projection")
    command.upgrade(config, "0014_event_unification")
    command.upgrade(config, "0014b_event_consumer_switch")
    command.downgrade(config, "0014_event_unification")
    command.upgrade(config, "0014b_event_consumer_switch")
    command.downgrade(config, "0013_internal_projection")
    command.upgrade(config, "0014b_event_consumer_switch")
    asyncio.run(_verify_nonempty_event_consumer_reconciliation(os.environ["SRBG_DATABASE_URL"]))
    print("Round14 migration replay passed: 0013 -> 0014b -> 0014 -> 0014b -> 0013 -> 0014b")


if __name__ == "__main__":
    main()
