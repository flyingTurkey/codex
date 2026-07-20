import json
import os
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings
from srbg_api.database import create_projection_reader_engine, create_publication_engine
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService, ProjectionNotFound

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 20, 3, 0, tzinfo=UTC)


async def test_reader_appendix_combines_current_facts_and_fails_closed_for_r3() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    admin = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    reader = PostgresV2IntelligenceService(
        create_projection_reader_engine(settings), create_publication_engine(settings)
    )
    try:
        async with admin.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            assert source_id is not None
            raw_id, document_id, version_id = uuid7(), uuid7(), uuid7()
            page_id, block_id = uuid7(), uuid7()
            item_id, event_id, claim_id, evidence_id, case_id = (
                uuid7(), uuid7(), uuid7(), uuid7(), uuid7()
            )
            await connection.execute(
                text(
                    "INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,"
                    "detected_mime,scan_status,created_at) VALUES(:id,repeat('1',64),"
                    "'t11/raw',20,'application/pdf','application/pdf','CLEAN',:now)"
                ),
                {"id": raw_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO document(id,source_id,canonical_url,document_kind,"
                    "first_discovered_at) VALUES(:id,:source,:url,'PDF',:now)"
                ),
                {
                    "id": document_id,
                    "source": source_id,
                    "url": "https://example.gov.cn/t11/source",
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version(id,document_id,raw_object_id,version_number,"
                    "content_hash,original_filename,acquired_at) VALUES(:id,:document,:raw,1,"
                    "repeat('2',64),'t11.pdf',:now)"
                ),
                {"id": version_id, "document": document_id, "raw": raw_id, "now": NOW},
            )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version WHERE id=:document"),
                {"version": version_id, "document": document_id},
            )
            excerpt = "该材料为有权机关发布的最终事故调查报告。"
            await connection.execute(
                text(
                    "INSERT INTO document_page(id,document_version_id,page_number,width_mpt,"
                    "height_mpt,rotation,text_source,normalized_text_sha256,preview_object_key,"
                    "preview_sha256,preview_mime,created_at) VALUES(:id,:version,1,595000,"
                    "842000,0,'NATIVE',repeat('3',64),'t11/preview',repeat('4',64),"
                    "'image/png',:now)"
                ),
                {"id": page_id, "version": version_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO document_text_block(id,document_page_id,block_index,block_kind,"
                    "text_source,text,normalized_text,text_sha256,x0_mpt,y0_mpt,x1_mpt,y1_mpt,"
                    "confidence_bps,created_at) VALUES(:id,:page,0,'BODY','NATIVE',:excerpt,"
                    ":excerpt,repeat('5',64),1000,1000,100000,20000,10000,:now)"
                ),
                {"id": block_id, "page": page_id, "excerpt": excerpt, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO intelligence_item(id,source_id,primary_document_id,"
                    "current_document_version_id,item_type,channel,risk_level,title,original_url,"
                    "source_published_at,first_discovered_at,activity_at,processing_status,"
                    "review_status,submitted_by,is_demo,publishable,created_at,updated_at) VALUES("
                    ":id,:source,:document,:version,'SAFETY_CASE','SAFETY','R2',:title,:url,"
                    ":now,:now,:now,'READY','APPROVED',:owner,false,true,:now,:now)"
                ),
                {
                    "id": item_id,
                    "source": source_id,
                    "document": document_id,
                    "version": version_id,
                    "title": "铁路隧道事故最终调查",
                    "url": "https://example.gov.cn/t11/source",
                    "owner": uuid7(),
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO event(id,event_type,title,subject_names,confirmation_status,"
                    "confirmed_by,confirmed_at,created_at,updated_at) VALUES(:id,'SAFETY_INCIDENT',"
                    ":title,'[]'::jsonb,'CONFIRMED',:owner,:now,:now,:now)"
                ),
                {"id": event_id, "title": "铁路隧道事故", "owner": uuid7(), "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO event_identity_binding(event_id,item_id,binding_kind,created_by,"
                    "created_at,rule_version,identity_key) VALUES(:event,:item,"
                    "'ROUND14_ONE_TO_ONE',:owner,:now,'t11-v1',:key)"
                ),
                {
                    "event": event_id,
                    "item": item_id,
                    "owner": uuid7(),
                    "now": NOW,
                    "key": f"t11:{item_id}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim(id,item_id,document_version_id,claim_type,subject,predicate,"
                    "literal_value,verification_status,critical,created_at,acceptance_method) "
                    "VALUES(:id,:item,:version,'report_stage','事故材料','阶段',"
                    "to_jsonb('最终调查'::text),'ACCEPTED',false,:now,'HUMAN_REVIEW')"
                ),
                {"id": claim_id, "item": item_id, "version": version_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence(id,claim_id,document_version_id,evidence_role,"
                    "excerpt,excerpt_sha256,original_url,created_at,locator_type,page_number,"
                    "document_text_block_id,x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps) VALUES("
                    ":id,:claim,:version,'PRIMARY_OFFICIAL',:excerpt,:hash,:url,:now,"
                    "'PDF_TEXT',1,:block,1000,1000,100000,20000,10000)"
                ),
                {
                    "id": evidence_id,
                    "claim": claim_id,
                    "version": version_id,
                    "excerpt": excerpt,
                    "hash": sha256(excerpt.encode()).hexdigest(),
                    "url": "https://example.gov.cn/t11/source",
                    "now": NOW,
                    "block": block_id,
                },
            )
            claim_payload = {
                "id": str(claim_id),
                "claim_type": "report_stage",
                "label": "阶段",
                "value": "最终调查",
                "evidence_ids": [str(evidence_id)],
                "decision_status": "ACCEPTED",
            }
            await connection.execute(
                text(
                    "INSERT INTO intelligence_projection_v2(event_id,document_version_id,"
                    "projection_kind,primary_type,risk_tier,payload,appendix_payload,generation,"
                    "projected_at) VALUES(:event,:version,'FULL','SAFETY_INTELLIGENCE','R2',"
                    "'{}'::jsonb,CAST(:appendix AS jsonb),1,:now)"
                ),
                {
                    "event": event_id,
                    "version": version_id,
                    "appendix": json.dumps(
                        {"event_id": str(event_id), "claims": [claim_payload]}
                    ),
                    "now": NOW,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO owner_review_case_v2(id,event_id,document_version_id,reason,"
                    "risk_tier,safe_metadata,state,version,created_at,updated_at) VALUES("
                    ":id,:event,:version,'T11_REVIEW','R2','{}'::jsonb,'RESOLVED',1,:now,:now)"
                ),
                {"id": case_id, "event": event_id, "version": version_id, "now": NOW},
            )
            await connection.execute(
                text(
                    "INSERT INTO personal_signal_projection(id,event_id,item_id,"
                    "document_version_id,judgment_version_id,result_type,payload,visible,"
                    "generation,created_at,updated_at) VALUES(:id,:event,:item,:version,NULL,"
                    "'EVIDENCE_FACT',CAST(:payload AS jsonb),"
                    "true,1,:now,:now)"
                ),
                {
                    "id": uuid7(),
                    "event": event_id,
                    "item": item_id,
                    "version": version_id,
                    "payload": json.dumps(
                        {
                            "title": "自动抽取阶段候选",
                            "original_url": "https://example.gov.cn/t11/source",
                        }
                    ),
                    "now": NOW,
                },
            )

        appendix = await reader.appendix(event_id)
        assert appendix.claims[0].id == claim_id
        assert appendix.evidence[0].id == evidence_id
        assert appendix.automatic_results[0].result_type == "EVIDENCE_FACT"
        assert appendix.review_context is not None
        assert appendix.review_context.case_id == case_id
        assert appendix.content_summary.total_items == 3

        async with admin.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE intelligence_projection_v2 SET projection_kind='R3_METADATA',"
                    "risk_tier='R3' WHERE event_id=:event"
                ),
                {"event": event_id},
            )
        with pytest.raises(ProjectionNotFound):
            await reader.appendix(event_id)
    finally:
        await reader.close()
        await admin.dispose()
