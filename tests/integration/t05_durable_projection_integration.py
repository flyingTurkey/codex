import json
import os
from base64 import b64decode
from datetime import UTC, datetime
from hashlib import sha256
from time import time
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from redis.asyncio import from_url
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings
from srbg_api.database import create_projection_reader_engine, create_publication_engine
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.content_candidates import (
    AcceptedClaimInput,
    ClaimEvidenceInput,
    accepted_claim_set_sha256,
)
from srbg_api.intelligence_v2.media import MediaDeliveryService, MediaRightsFact
from srbg_api.intelligence_v2.media_repository import PostgresMediaDeliveryRepository
from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService, ProjectionNotFound
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_contracts import HotspotCandidateV2

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 7, 20, 2, 0, tzinfo=UTC)
OWNER_ID = UUID("019f8400-0000-7000-8000-000000000001")
SAFE_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


async def test_full_r3_r4_archive_and_retry_are_durable_and_fail_closed() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    publication_repository = PostgresPublicationRepository(create_publication_engine(settings))
    publication = PublicationService(
        repository=publication_repository,
        gate=object(),  # type: ignore[arg-type]
        now=lambda: NOW,
    )
    media_repository = PostgresMediaDeliveryRepository(create_publication_engine(settings))
    store = S3ObjectStore(settings)
    reader = PostgresV2IntelligenceService(
        create_projection_reader_engine(settings),
        create_publication_engine(settings),
        store,
    )
    redis = from_url(settings.redis_url, socket_timeout=settings.external_io_timeout_seconds)
    try:
        async with admin.begin() as connection:
            source_id = await connection.scalar(
                text(
                    "SELECT id FROM source WHERE authority_level IN ('A0','A1') "
                    "ORDER BY id LIMIT 1"
                )
            )
            assert source_id is not None
            raw_id = uuid7()
            document_id = uuid7()
            version_id = uuid7()
            page_id = uuid7()
            block_id = uuid7()
            item_id = uuid7()
            event_id = uuid7()
            claim_id = uuid7()
            evidence_id = uuid7()
            title = "铁路隧道安全整治权威通报"
            original_url = "https://example.gov.cn/t05/fixture"
            fixture = {
                "event_id": event_id,
                "item_id": item_id,
                "version_id": version_id,
                "title": title,
                "original_url": original_url,
            }
            await connection.execute(
                text(
                    "INSERT INTO raw_object("
                    "id,sha256,object_key,byte_size,declared_mime,detected_mime,scan_status,"
                    "created_at) VALUES(:id,repeat('1',64),'t05/raw',20,'application/pdf',"
                    "'application/pdf','CLEAN',:now)"
                ),
                {"id": raw_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO raw_object_security_fact("
                    "id,raw_object_id,status,detected_mime,rule_version,created_at) VALUES("
                    ":id,:raw_id,'CLEAN','application/pdf',"
                    "'t05-protocol-security-fixture-v1',:now)"
                ),
                {"id": uuid7(), "raw_id": raw_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO document("
                    "id,source_id,canonical_url,document_kind,first_discovered_at) "
                    "VALUES(:id,:source_id,:url,'PDF',:now)"
                ),
                {"id": document_id, "source_id": source_id, "url": original_url, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version("
                    "id,document_id,raw_object_id,version_number,content_hash,original_filename,"
                    "acquired_at) VALUES(:id,:document_id,:raw_id,1,repeat('2',64),"
                    "'fixture.pdf',:now)"
                ),
                {"id": version_id, "document_id": document_id, "raw_id": raw_id, "now": NOW},
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version_id WHERE id=:document_id"),
                {"version_id": version_id, "document_id": document_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_page("
                    "id,document_version_id,page_number,width_mpt,height_mpt,rotation,text_source,"
                    "normalized_text_sha256,preview_object_key,preview_sha256,preview_mime,"
                    "created_at) VALUES(:id,:version_id,1,595000,842000,0,'NATIVE',"
                    "repeat('3',64),'t05/preview',repeat('4',64),'image/png',:now)"
                ),
                {"id": page_id, "version_id": version_id, "now": NOW},
            )
            excerpt = "铁路隧道正在开展安全隐患整治。"
            await connection.execute(
                text(
                    "INSERT INTO document_text_block("
                    "id,document_page_id,block_index,block_kind,text_source,text,normalized_text,"
                    "text_sha256,x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps,created_at) VALUES("
                    ":id,:page_id,0,'BODY','NATIVE',:excerpt,:excerpt,repeat('5',64),"
                    "1000,1000,100000,20000,10000,:now)"
                ),
                {"id": block_id, "page_id": page_id, "excerpt": excerpt, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO intelligence_item("
                    "id,source_id,primary_document_id,current_document_version_id,item_type,"
                    "channel,risk_level,title,original_url,source_published_at,"
                    "first_discovered_at,activity_at,processing_status,review_status,"
                    "submitted_by,is_demo,publishable,created_at,updated_at) VALUES("
                    ":id,:source_id,:document_id,:version_id,'SAFETY_CASE','SAFETY','R3',"
                    ":title,:url,NULL,:now,:now,'READY','PENDING',:owner,false,false,:now,:now)"
                ),
                {
                    "id": item_id,
                    "source_id": source_id,
                    "document_id": document_id,
                    "version_id": version_id,
                    "title": title,
                    "url": original_url,
                    "owner": OWNER_ID,
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO event("
                    "id,event_type,title,subject_names,confirmation_status,confirmed_by,"
                    "confirmed_at,created_at,updated_at) VALUES("
                    ":id,'SAFETY_INCIDENT',:title,'[]'::jsonb,'CONFIRMED',:owner,:now,:now,:now)"
                ),
                {"id": event_id, "title": title, "owner": OWNER_ID, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO event_identity_binding("
                    "event_id,item_id,binding_kind,created_by,created_at,rule_version,"
                    "identity_key) "
                    "VALUES(:event_id,:item_id,'ROUND14_ONE_TO_ONE',:owner,:now,'t05-v1',:key)"
                ),
                {
                    "event_id": event_id,
                    "item_id": item_id,
                    "owner": OWNER_ID,
                    "now": NOW,
                    "key": f"t05:{item_id}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim("
                    "id,item_id,document_version_id,claim_type,subject,predicate,literal_value,"
                    "verification_status,critical,created_at,acceptance_method) VALUES("
                    ":id,:item_id,:version_id,'safety_measure','铁路隧道','开展',"
                    "to_jsonb('安全隐患整治'::text),'ACCEPTED',false,:now,'HUMAN_REVIEW')"
                ),
                {"id": claim_id, "item_id": item_id, "version_id": version_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence("
                    "id,claim_id,document_version_id,evidence_role,excerpt,excerpt_sha256,"
                    "original_url,created_at,locator_type,page_number,document_text_block_id,"
                    "x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps) VALUES("
                    ":id,:claim_id,:version_id,'PRIMARY_OFFICIAL',:excerpt,:hash,:url,:now,"
                    "'PDF_TEXT',1,:block_id,1000,1000,100000,20000,10000)"
                ),
                {
                    "id": evidence_id,
                    "claim_id": claim_id,
                    "version_id": version_id,
                    "excerpt": excerpt,
                    "hash": sha256(excerpt.encode()).hexdigest(),
                    "url": original_url,
                    "now": NOW,
                    "block_id": block_id,
                },
            )
            claim_ids = [claim_id]
            current_claim_hash = accepted_claim_set_sha256(
                [
                    AcceptedClaimInput(
                        claim_id=claim_id,
                        document_version_id=version_id,
                        field_name="safety_measure",
                        value="安全隐患整治",
                        basis="PROJECT_FIRST_PARTY_RECORD",
                        active=True,
                        evidence=(
                            ClaimEvidenceInput(
                                evidence_id=evidence_id,
                                document_version_id=version_id,
                                document_block_id=block_id,
                                locator="PDF_TEXT:page:1",
                                excerpt=excerpt,
                                char_start=0,
                                char_end=len(excerpt),
                            ),
                        ),
                    )
                ]
            )
            run_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO ai_pipeline_run("
                    "id,document_version_id,mode,status,input_sha256,started_at,completed_at) "
                    "VALUES(:id,:version_id,'SHADOW','SUCCEEDED',repeat('a',64),:now,:now)"
                ),
                {"id": run_id, "version_id": fixture["version_id"], "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO qualification_acceptance_v2("
                    "id,event_id,document_version_id,pipeline_run_id,primary_type,"
                    "engineering_objects,specialty_facets,equipment_domains,cross_type_tags,"
                    "classification_sha256,accepted_at) VALUES("
                    ":id,:event_id,:version_id,:run_id,'SAFETY_INTELLIGENCE',"
                    "ARRAY['RAILWAY','TUNNEL'],ARRAY[]::text[],ARRAY[]::text[],"
                    "ARRAY[]::text[],repeat('b',64),:now)"
                ),
                {"id": uuid7(), "run_id": run_id, "now": NOW, **fixture},
            )
            paragraphs = [
                {
                    "kind": "FACT",
                    "section": "WHAT_HAPPENED",
                    "text": "事实" * 50,
                    "claim_ids": [str(value) for value in claim_ids],
                },
                {
                    "kind": "JUDGMENT",
                    "section": "ENGINEERING_IMPACT",
                    "text": "影响" * 50,
                    "claim_ids": [],
                    "judgment_type": "ENGINEERING_SIGNIFICANCE",
                },
                {
                    "kind": "JUDGMENT",
                    "section": "LIMITATIONS_AND_FOLLOW_UP",
                    "text": "限制" * 50,
                    "claim_ids": [],
                    "judgment_type": "LIMITATION_AND_FOLLOW_UP",
                },
            ]
            claims_payload = [
                {
                    "claim_id": str(claim_id),
                    "basis": "AUTHORITY_FINDING",
                    "evidence_locators": [f"claim:{claim_id}"],
                }
                for claim_id in claim_ids
            ]
            await connection.execute(
                text(
                    "INSERT INTO content_preparation_candidate_v2("
                    "id,event_id,document_version_id,accepted_claim_set_sha256,source_excerpt,"
                    "claim_ids,source_excerpt_claim_ids,evidence_locators,claim_basis,"
                    "claims_payload,summary_payload,visible_character_count,model,prompt_version,"
                    "schema_version,input_sha256,created_at) VALUES("
                    ":id,:event_id,:version_id,:claim_hash,'权威原文摘录',:claim_ids,"
                    ":claim_ids,ARRAY['html:p:1'],ARRAY['AUTHORITY_FINDING'],"
                    "CAST(:claims AS jsonb),CAST(:summary AS jsonb),300,'protocol-test-stub',"
                    "'t05-test-v1','summarize-v2-output-v1',repeat('d',64),:now)"
                ),
                {
                    "id": uuid7(),
                    "claim_hash": current_claim_hash,
                    "claim_ids": claim_ids,
                    "claims": json.dumps(claims_payload),
                    "summary": json.dumps(
                        {"visible_character_count": 300, "paragraphs": paragraphs}
                    ),
                    "now": NOW,
                    **fixture,
                },
            )
            case_id = uuid7()
            safe_metadata = {
                "title": fixture["title"],
                "primary_type": "SAFETY_INTELLIGENCE",
                "official_source": True,
                "original_url": fixture["original_url"],
            }
            await connection.execute(
                text(
                    "INSERT INTO owner_review_case_v2("
                    "id,event_id,document_version_id,reason,risk_tier,safe_metadata,state,"
                    "version,created_at,updated_at) VALUES("
                    ":id,:event_id,:version_id,'T05_REVIEW','R3',CAST(:metadata AS jsonb),"
                    "'OPEN',1,:now,:now)"
                ),
                {
                    "id": case_id,
                    "metadata": json.dumps(safe_metadata, ensure_ascii=False),
                    "now": NOW,
                    **fixture,
                },
            )
            await connection.execute(
                text("UPDATE intelligence_item SET risk_level='R3' WHERE id=:item_id"), fixture
            )
            image = SAFE_PNG
            image_hash = sha256(image).hexdigest()
            object_key = f"sha256/{image_hash[:2]}/{image_hash}"
            image_raw_id = uuid7()
            attachment_id = uuid7()
            media_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO raw_object("
                    "id,sha256,object_key,byte_size,declared_mime,detected_mime,scan_status,"
                    "created_at) VALUES(:id,:hash,:key,:size,'image/png','image/png','CLEAN',:now)"
                ),
                {
                    "id": image_raw_id,
                    "hash": image_hash,
                    "key": object_key,
                    "size": len(image),
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_attachment("
                    "id,document_version_id,raw_object_id,filename,role,created_at,"
                    "parent_attachment_id,normalized_path,depth,detected_mime,byte_size,"
                    "security_status) VALUES(:id,:version_id,:raw_id,'许可图片.png',"
                    "'SOURCE_ATTACHMENT',:now,NULL,'许可图片.png',0,'image/png',:size,'CLEAN')"
                ),
                {
                    "id": attachment_id,
                    "version_id": version_id,
                    "raw_id": image_raw_id,
                    "size": len(image),
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_attachment_attempt("
                    "id,document_version_id,content_sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,filename_sha256,normalized_path_sha256,canonical_url_sha256,"
                    "outcome,occurred_at) VALUES(:id,:version_id,:hash,:key,:size,'image/png',"
                    "'image/png',:name_hash,:name_hash,:url_hash,'ACCEPTED',:now)"
                ),
                {
                    "id": uuid7(),
                    "version_id": version_id,
                    "hash": image_hash,
                    "key": object_key,
                    "size": len(image),
                    "name_hash": sha256("许可图片.png".encode()).hexdigest(),
                    "url_hash": sha256(original_url.encode()).hexdigest(),
                    "now": NOW,
                },
            )
        await store.put_if_absent(object_key, image, "image/png")
        await MediaDeliveryService(
            media_repository,
            store,
        ).register(
            MediaRightsFact(
                media_id=media_id,
                attachment_id=attachment_id,
                source_url=original_url,
                rights_basis="SOURCE_AUTHORIZED",
                rights_evidence_ref="t05-protocol-rights-fixture-v1",
                redistribution_allowed=True,
            )
        )

        await publication.refresh_v2_projection(
            event_id=fixture["event_id"], document_version_id=fixture["version_id"]
        )
        metadata = await reader.event(fixture["event_id"])
        assert metadata.projection_kind == "R3_METADATA"
        assert set(metadata.model_dump(mode="json")) == {
            "projection_kind",
            "event_id",
            "title",
            "primary_type",
            "official_source",
            "source_name",
            "source_published_at",
            "first_discovered_at",
            "original_url",
            "review_state",
        }
        r3_search = await reader.search(query="隧道", limit=20)
        assert len(r3_search.items) == 1
        assert r3_search.items[0].projection_kind == "R3_METADATA"
        assert "search_explanation" not in r3_search.items[0].model_dump(mode="json")

        async with admin.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE owner_review_case_v2 SET risk_tier='R2',state='RESOLVED',"
                    "updated_at=:now WHERE id=:id"
                ),
                {"id": case_id, "now": NOW},
            )
        await publication.refresh_v2_projection(
            event_id=fixture["event_id"], document_version_id=fixture["version_id"]
        )
        await publication.refresh_v2_projection(
            event_id=fixture["event_id"], document_version_id=fixture["version_id"]
        )
        full = await reader.event(fixture["event_id"])
        assert full.projection_kind == "FULL"
        assert full.source.official is True
        assert full.human_reviewed is False
        evidence_search = await reader.search(query="原文摘录", limit=20)
        assert len(evidence_search.items) == 1
        evidence_result = evidence_search.items[0]
        assert evidence_result.projection_kind == "FULL"
        assert evidence_result.search_explanation is not None
        assert evidence_result.search_explanation.matched_evidence_fields == ["SOURCE_EXCERPT"]
        assert evidence_result.search_explanation.ai_summary_assisted is False
        ai_search = await reader.search(query="影响", limit=20)
        assert len(ai_search.items) == 1
        ai_result = ai_search.items[0]
        assert ai_result.projection_kind == "FULL"
        assert ai_result.search_explanation is not None
        assert ai_result.search_explanation.matched_evidence_fields == []
        assert ai_result.search_explanation.ai_summary_assisted is True
        preview, mime_type = await reader.media_preview(full.media[0].media_id)
        assert mime_type == "image/png"
        assert preview.startswith(b"\x89PNG\r\n\x1a\n")
        assert preview != image
        signed_download = await reader.media_download(
            full.media[0].media_id, max_age_seconds=900
        )
        expires_at = int(parse_qs(urlsplit(signed_download).query)["Expires"][0])
        assert 295 <= expires_at - int(time()) <= 300

        async with admin.begin() as connection:
            await connection.execute(
                text("UPDATE media_rights_v2 SET scan_status='PENDING' WHERE id=:id"),
                {"id": full.media[0].media_id},
            )
        with pytest.raises(ProjectionNotFound):
            await reader.media_preview(full.media[0].media_id)
        with pytest.raises(ProjectionNotFound):
            await reader.media_download(full.media[0].media_id, max_age_seconds=300)
        async with admin.begin() as connection:
            await connection.execute(
                text("UPDATE media_rights_v2 SET scan_status='CLEAN' WHERE id=:id"),
                {"id": full.media[0].media_id},
            )

        async with admin.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE intelligence_item SET source_published_at=:now "
                    "WHERE id=:item_id"
                ),
                {"now": NOW, **fixture},
            )
            await connection.execute(
                text(
                    "INSERT INTO source_admission_assessment_v2("
                    "id,source_id,rule_version,sample_cutoff,lookback_days,sample_size,"
                    "sample_manifest_sha256,metrics,evidence_refs,verdict,assessed_by,"
                    "assessed_at) VALUES(:id,:source_id,'t09-protocol-fixture-v1',:now,90,1,"
                    "repeat('9',64),'{}'::jsonb,'[]'::jsonb,'ADMIT',:owner,:now)"
                ),
                {
                    "id": uuid7(),
                    "source_id": source_id,
                    "owner": OWNER_ID,
                    "now": NOW,
                },
            )
            score_set_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO score_set(id,item_id,rule_version,calculated_at,is_current) "
                    "VALUES(:id,:item_id,'t09-server-score-fixture-v1',:now,true)"
                ),
                {"id": score_set_id, "item_id": item_id, "now": NOW},
            )
            for dimension, raw_score in (
                ("IMPACT", 80),
                ("RELEVANCE", 80),
                ("NOVELTY", 75),
                ("TIMELINESS", 67),
                ("AUTHORITY", 67),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO score_dimension("
                        "id,score_set_id,dimension,raw_score,features) "
                        "VALUES(:id,:score_set_id,:dimension,:raw_score,'{}'::jsonb)"
                    ),
                    {
                        "id": uuid7(),
                        "score_set_id": score_set_id,
                        "dimension": dimension,
                        "raw_score": raw_score,
                    },
                )
        await publication.append_hotspot_candidate(
            event_id=event_id,
            document_version_id=version_id,
            candidate=HotspotCandidateV2(
                claim_ids=[claim_id],
                reasons=[
                    {
                        "text": "权威一手材料说明铁路隧道整治具有重大工程影响",
                        "claim_ids": [claim_id],
                    }
                ],
            ),
            model="protocol-test-stub",
            prompt_version="t09-test-v1",
            schema_version="hotspot-candidate-v2",
            input_sha256="8" * 64,
        )
        first_award = await publication.evaluate_hotspot(
            event_id=event_id, document_version_id=version_id
        )
        second_award = await publication.evaluate_hotspot(
            event_id=event_id, document_version_id=version_id
        )
        assert first_award.awarded is True
        assert first_award.trigger == "AUTHORITY_SCORE"
        assert first_award.score == 75
        assert second_award.awarded is True
        hotspot_page = await reader.hotspots(limit=20)
        assert len(hotspot_page.items) == 1
        hotspot_projection = hotspot_page.items[0]
        assert hotspot_projection.projection_kind == "FULL"
        assert hotspot_projection.primary_type.value == "SAFETY_INTELLIGENCE"
        assert hotspot_projection.hotspot is not None
        assert hotspot_projection.hotspot.trigger == "AUTHORITY_SCORE"
        assert "score" not in hotspot_projection.hotspot.model_dump(mode="json")
        async with admin.connect() as connection:
            counts = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM hotspot_evaluation_v2 "
                        "WHERE event_id=:event_id) evaluation_count,"
                        "(SELECT count(*) FROM hotspot_award_v2 "
                        "WHERE event_id=:event_id AND evaluation_id IS NOT NULL) award_count"
                    ),
                    fixture,
                )
            ).one()
            assert tuple(counts) == (2, 2)
            replay_inputs = await connection.scalar(
                text(
                    "SELECT evaluation_inputs FROM hotspot_evaluation_v2 "
                    "WHERE event_id=:event_id ORDER BY evaluated_at DESC,id DESC LIMIT 1"
                ),
                fixture,
            )
            assert replay_inputs["score_rule_versions"] == ["t09-server-score-fixture-v1"]
            assert replay_inputs["sources"][0]["source_id"] == str(source_id)
            assert replay_inputs["sources"][0]["accepted_claim_ids"] == [str(claim_id)]
        with pytest.raises(DBAPIError, match="T09_APPEND_ONLY_FACT"):
            async with admin.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE hotspot_award_v2 SET revoked_at=:now "
                        "WHERE event_id=:event_id AND evaluation_id IS NOT NULL"
                    ),
                    {"now": NOW, **fixture},
                )

        await redis.set(f"t05:{fixture['event_id']}", full.model_dump_json(), ex=60)
        assert await redis.get(f"t05:{fixture['event_id']}") == full.model_dump_json().encode()

        archive_bytes = b"published_v1.event_projection_revision\x00fixture-row\x00" + (
            b"e" * 64
        ) + b"\n"
        archive_hash = sha256(archive_bytes).hexdigest()
        archive_key = f"t05/archive/{archive_hash}"
        await store.put_if_absent(archive_key, archive_bytes, "application/x-ndjson")
        async with admin.begin() as connection:
            manifest_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO projection_archive_manifest("
                    "id,generation,object_key,sha256,row_count,audit_tail_anchor,created_at) "
                    "VALUES(:id,'v1',:key,:hash,1,'t05-fixture-anchor',:now)"
                ),
                {"id": manifest_id, "key": archive_key, "hash": archive_hash, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO projection_archive_row_v2("
                    "id,manifest_id,source_table,row_key,row_sha256) VALUES("
                    ":id,:manifest,'published_v1.event_projection_revision','fixture-row',"
                    "repeat('e',64))"
                ),
                {"id": uuid7(), "manifest": manifest_id},
            )
            counts = (
                await connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM intelligence_projection_v2 "
                        "WHERE event_id=:event_id) projection_count,"
                        "(SELECT count(*) FROM content_preparation_candidate_v2 "
                        "WHERE event_id=:event_id) candidate_count,"
                        "(SELECT count(*) FROM media_rights_v2 "
                        "WHERE document_version_id=:version_id) media_count"
                    ),
                    fixture,
                )
            ).one()
            assert tuple(counts) == (1, 1, 1)
        assert sha256(await store.get_bytes(archive_key)).hexdigest() == archive_hash

        async with admin.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE owner_review_case_v2 SET risk_tier='R4',state='QUARANTINED',"
                    "reason='UNRESOLVED_PROMPT_INJECTION',updated_at=:now WHERE id=:id"
                ),
                {"id": case_id, "now": NOW},
            )
        with pytest.raises(PublicationDenied, match="R4_CANNOT_ENTER_READER_PROJECTION"):
            await publication.refresh_v2_projection(
                event_id=fixture["event_id"], document_version_id=fixture["version_id"]
            )
        with pytest.raises(ProjectionNotFound):
            await reader.event(fixture["event_id"])
        quarantine = await reader.quarantine(case_id)
        assert quarantine.isolation_reason == "UNRESOLVED_PROMPT_INJECTION"
        assert "source_excerpt" not in quarantine.model_dump(mode="json")
    finally:
        await redis.aclose()
        await reader.close()
        await media_repository.close()
        await publication.close()
        await admin.dispose()
        get_settings.cache_clear()
