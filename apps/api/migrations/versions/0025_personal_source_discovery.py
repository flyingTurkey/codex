# ruff: noqa: E501, S608 -- fixed migration SQL remains auditable inline.
"""PERS-05 editable topics, bounded discovery scoring and personal auto-enablement.

Revision ID: 0025_personal_source_discovery
Revises: 0024_automatic_source_profiles
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from srbg_api.identifiers import uuid7

revision = "0025_personal_source_discovery"
down_revision = "0024_automatic_source_profiles"
branch_labels = None
depends_on = None

LOCAL_OWNER_ID = "019b0000-0000-7000-8000-000000009001"

TOPICS = (
    ("HIGHWAY", "公路", ["公路", "高速公路", "道路工程"]),
    ("BRIDGE", "桥梁", ["桥梁", "桥涵"]),
    ("TUNNEL", "隧道", ["隧道", "地下工程"]),
    ("RAIL", "铁路/轨道", ["铁路", "轨道交通", "城市轨道", "地铁"]),
    ("DIGITAL", "数字化", ["数字化", "数字孪生", "智慧建造", "BIM"]),
    (
        "AI_IOT_LOW_ALTITUDE",
        "AI、物联网和低空设备",
        ["AI", "人工智能", "物联网", "IoT", "低空", "无人机", "智能设备"],
    ),
    (
        "SAFETY",
        "安全法规、标准、事故、处罚和整改",
        ["安全法规", "安全规定", "标准", "指南", "事故调查", "通报", "处罚", "整改"],
    ),
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "discovery_topic",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("excluded_terms", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("focus_regions", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "code IN ('HIGHWAY','BRIDGE','TUNNEL','RAIL','DIGITAL','AI_IOT_LOW_ALTITUDE','SAFETY')",
            name="ck_discovery_topic_code",
        ),
        sa.CheckConstraint(
            "cardinality(keywords) BETWEEN 1 AND 50 AND cardinality(excluded_terms)<=50 AND cardinality(focus_regions)<=50",
            name="ck_discovery_topic_term_counts",
        ),
        sa.CheckConstraint("version>=1", name="ck_discovery_topic_version"),
    )
    op.create_table(
        "discovery_topic_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "topic_id", _uuid(), sa.ForeignKey("discovery_topic.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE TRIGGER trg_discovery_topic_event_append_only BEFORE UPDATE OR DELETE "
        "ON discovery_topic_event FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )
    op.create_table(
        "personal_discovery_setting_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("before_enabled", sa.Boolean(), nullable=False),
        sa.Column("after_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "CREATE TRIGGER trg_personal_discovery_setting_event_append_only BEFORE UPDATE OR DELETE "
        "ON personal_discovery_setting_event FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    op.create_table(
        "discovery_occurrence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "topic_id", _uuid(), sa.ForeignKey("discovery_topic.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("canonical_origin", sa.String(2048), nullable=False),
        sa.Column("canonical_origin_sha256", sa.String(64), nullable=False),
        sa.Column("discovery_channel", sa.String(30), nullable=False),
        sa.Column("parent_source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column("expansion_depth", sa.SmallInteger(), nullable=False),
        sa.Column("candidate_id", _uuid(), sa.ForeignKey("source_candidate.id", ondelete="RESTRICT")),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_PROBE"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("expansion_depth IN (0,1)", name="ck_discovery_occurrence_depth"),
        sa.CheckConstraint("occurrence_count>=1", name="ck_discovery_occurrence_count"),
        sa.CheckConstraint(
            "canonical_origin ~ '^https://[^[:space:]@]+/$' AND canonical_origin_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_discovery_occurrence_origin",
        ),
        sa.CheckConstraint(
            "discovery_channel IN ('RSS','SITEMAP','OUTBOUND_LINK','BAIDU_SEARCH')",
            name="ck_discovery_occurrence_channel",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_PROBE','PROBING','PROFILE_PENDING','SCORED','DEFERRED','REJECTED','ENABLED')",
            name="ck_discovery_occurrence_status",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_discovery_occurrence_identity ON discovery_occurrence "
        "(topic_id,canonical_origin_sha256,discovery_channel,COALESCE(parent_source_id,'00000000-0000-0000-0000-000000000000'::uuid))"
    )
    op.create_index(
        "ix_discovery_occurrence_queue",
        "discovery_occurrence",
        ["status", "first_discovered_at", "id"],
    )

    _create_daily_ledger("personal_probe_daily_ledger", 100)
    _create_daily_ledger("personal_auto_enable_daily_ledger", 20)

    op.create_table(
        "source_auto_score_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("occurrence_id", _uuid(), sa.ForeignKey("discovery_occurrence.id", ondelete="RESTRICT")),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", _uuid()),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETE','DEFERRED','FAILED')",
            name="ck_source_auto_score_run_status",
        ),
        sa.CheckConstraint(
            "reason IN ('DISCOVERED','EXISTING_SOURCE','PROFILE_UPDATED','EVIDENCE_UPDATED')",
            name="ck_source_auto_score_run_reason",
        ),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_source_auto_score_attempts"),
    )
    op.create_index(
        "uq_source_auto_score_active",
        "source_auto_score_run",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING','DEFERRED')"),
    )
    op.create_index(
        "ix_source_auto_score_queue",
        "source_auto_score_run",
        ["status", "next_attempt_at", "id"],
    )
    op.create_table(
        "source_auto_score_snapshot",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_id", _uuid(), sa.ForeignKey("source_auto_score_run.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("topic_relevance_score", sa.SmallInteger(), nullable=False),
        sa.Column("connector_stability_score", sa.SmallInteger(), nullable=False),
        sa.Column("sample_completeness_score", sa.SmallInteger(), nullable=False),
        sa.Column("profile_evidence_score", sa.SmallInteger(), nullable=False),
        sa.Column("content_validity_score", sa.SmallInteger(), nullable=False),
        sa.Column("total_score", sa.SmallInteger(), nullable=False),
        sa.Column("auto_enable_eligible", sa.Boolean(), nullable=False),
        sa.Column("hard_gate_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("component_explanations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("evidence_refs", postgresql.ARRAY(sa.String(500)), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "version", name="uq_source_auto_score_version"),
        sa.CheckConstraint("version>=1", name="ck_source_auto_score_version"),
        sa.CheckConstraint("topic_relevance_score BETWEEN 0 AND 35", name="ck_auto_score_relevance"),
        sa.CheckConstraint("connector_stability_score BETWEEN 0 AND 25", name="ck_auto_score_stability"),
        sa.CheckConstraint("sample_completeness_score BETWEEN 0 AND 20", name="ck_auto_score_completeness"),
        sa.CheckConstraint("profile_evidence_score BETWEEN 0 AND 10", name="ck_auto_score_profile"),
        sa.CheckConstraint("content_validity_score BETWEEN 0 AND 10", name="ck_auto_score_validity"),
        sa.CheckConstraint(
            "total_score=topic_relevance_score+connector_stability_score+sample_completeness_score+profile_evidence_score+content_validity_score",
            name="ck_auto_score_total",
        ),
        sa.CheckConstraint("evidence_sha256 ~ '^[0-9a-f]{64}$'", name="ck_auto_score_evidence_hash"),
    )
    op.create_index(
        "ix_source_auto_score_enable_queue",
        "source_auto_score_snapshot",
        ["auto_enable_eligible", "total_score", "evaluated_at", "id"],
    )
    op.execute(
        "CREATE TRIGGER trg_source_auto_score_snapshot_append_only BEFORE UPDATE OR DELETE "
        "ON source_auto_score_snapshot FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    _replace_source_event_constraint()
    _create_budget_functions()
    _seed_topics_and_score_queue()
    op.execute(
        "UPDATE personal_automation_setting SET automation_enabled=true,updated_at=now() "
        "WHERE singleton_slot=1"
    )
    op.execute(
        "GRANT SELECT ON discovery_topic,discovery_occurrence,personal_probe_daily_ledger,"
        "personal_auto_enable_daily_ledger,source_auto_score_run,source_auto_score_snapshot TO srbg_api_role"
    )
    op.execute("GRANT UPDATE ON discovery_topic,personal_automation_setting TO srbg_api_role")
    op.execute(
        "GRANT INSERT ON discovery_topic_event,personal_discovery_setting_event TO srbg_api_role"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON discovery_occurrence,personal_probe_daily_ledger,"
        "personal_auto_enable_daily_ledger,source_auto_score_run TO srbg_worker_role"
    )
    op.execute("GRANT SELECT,INSERT ON source_auto_score_snapshot TO srbg_worker_role")


def _create_daily_ledger(table: str, limit: int) -> None:
    op.create_table(
        table,
        sa.Column("local_date", sa.Date(), primary_key=True),
        sa.Column("used_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("daily_limit", sa.SmallInteger(), nullable=False, server_default=str(limit)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"daily_limit={limit} AND used_count BETWEEN 0 AND daily_limit",
            name=f"ck_{table}_bounds",
        ),
    )


def _replace_source_event_constraint() -> None:
    op.drop_constraint("ck_source_key_activity_event_type", "source_key_activity_event", type_="check")
    op.create_check_constraint(
        "ck_source_key_activity_event_type",
        "source_key_activity_event",
        "event_type IN ('MANUAL_DISABLED','MANUAL_ENABLED','DISPLAY_NAME_CHANGED','AUTO_ENABLED')",
    )


def _create_budget_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION personal_discovery_local_date(p_now timestamptz) RETURNS date
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT (p_now AT TIME ZONE 'Asia/Shanghai')::date
        $$
        """
    )
    for function, table, limit in (
        ("reserve_personal_probe_budget", "personal_probe_daily_ledger", 100),
        ("reserve_personal_auto_enable_budget", "personal_auto_enable_daily_ledger", 20),
    ):
        op.execute(
            f"""
            CREATE FUNCTION {function}(p_now timestamptz) RETURNS boolean
            LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
            DECLARE v_date date:=personal_discovery_local_date(p_now);v_used smallint;
            BEGIN
              INSERT INTO {table}(local_date,used_count,daily_limit,updated_at)
              VALUES(v_date,0,{limit},p_now) ON CONFLICT(local_date) DO NOTHING;
              UPDATE {table} SET used_count=used_count+1,updated_at=p_now
               WHERE local_date=v_date AND used_count<daily_limit RETURNING used_count INTO v_used;
              RETURN v_used IS NOT NULL;
            END $$
            """
        )
        op.execute(f"REVOKE ALL ON FUNCTION {function}(timestamptz) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {function}(timestamptz) TO srbg_worker_role")

    op.execute(
        """
        CREATE FUNCTION auto_enable_personal_source(
          p_source_id uuid,p_event_id uuid,p_outbox_id uuid,p_now timestamptz
        ) RETURNS boolean
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE v_source source%ROWTYPE;v_snapshot source_auto_score_snapshot%ROWTYPE;
        BEGIN
          SELECT * INTO v_source FROM source WHERE id=p_source_id FOR UPDATE;
          IF NOT FOUND OR v_source.manual_disabled_at IS NOT NULL OR v_source.enabled THEN
            RETURN false;
          END IF;
          SELECT * INTO v_snapshot FROM source_auto_score_snapshot
           WHERE source_id=p_source_id ORDER BY version DESC LIMIT 1;
          IF NOT FOUND OR v_snapshot.rule_version<>'personal-source-auto-score-v1'
             OR NOT v_snapshot.auto_enable_eligible OR v_snapshot.total_score<70
             OR COALESCE((v_snapshot.hard_gate_results->>'public_network')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'ssrf_safe')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'robots_permitted')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'access_open')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'terms_permitted')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'copyright_permitted')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'connector_executable')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'sample_parsed')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'evidence_current')::boolean,false)=false
             OR COALESCE((v_snapshot.hard_gate_results->>'sticky_disabled')::boolean,true)=true
             OR NOT EXISTS(
               SELECT 1 FROM source_profile_snapshot profile
               WHERE profile.source_id=p_source_id
                 AND profile.input_sha256=v_snapshot.evidence_sha256
                 AND profile.version=(SELECT MAX(latest.version)
                   FROM source_profile_snapshot latest
                   WHERE latest.source_id=p_source_id)
             )
             OR NOT EXISTS(
               SELECT 1 FROM source_stream stream
               JOIN stream_config_version config ON config.stream_id=stream.id
               JOIN stream_probe_run probe ON probe.id=config.probe_run_id
               WHERE stream.source_id=p_source_id AND stream.status='READY'
                 AND probe.status='SUCCEEDED' AND jsonb_array_length(probe.capture_manifest)>0
             ) THEN
            RETURN false;
          END IF;
          IF NOT reserve_personal_auto_enable_budget(p_now) THEN RETURN false; END IF;
          UPDATE source SET desired_enabled=true,enabled=true,state='ACTIVE',
            runtime_state='RUNNING',updated_at=p_now WHERE id=p_source_id;
          UPDATE source_stream SET status='ACTIVE',updated_at=p_now
            WHERE source_id=p_source_id AND status='READY';
          UPDATE fetch_schedule SET status='ACTIVE',lease_token=NULL,leased_until=NULL,
            next_run_at=p_now,updated_at=p_now WHERE source_id=p_source_id AND status='PAUSED';
          INSERT INTO source_key_activity_event(
            id,source_id,event_type,actor_id,request_id,before_state,after_state,created_at
          ) VALUES(
            p_event_id,p_source_id,'AUTO_ENABLED',
            '019b0000-0000-7000-8000-000000009001'::uuid,
            'pers05-auto-enable',
            jsonb_build_object('enabled',false,'desired_enabled',v_source.desired_enabled),
            jsonb_build_object('enabled',true,'desired_enabled',true,
              'score',v_snapshot.total_score,'rule_version',v_snapshot.rule_version),p_now
          );
          INSERT INTO outbox_event(
            id,event_type,aggregate_type,aggregate_id,payload,status,attempt_count,
            available_at,created_at
          ) VALUES(
            p_outbox_id,'PERSONAL_SOURCE_AUTO_ENABLED','source',p_source_id,
            jsonb_build_object('source_id',p_source_id,'score',v_snapshot.total_score,
              'rule_version',v_snapshot.rule_version),
            'PENDING',0,p_now,p_now
          );
          UPDATE discovery_occurrence SET status='ENABLED',last_discovered_at=p_now
            WHERE source_id=p_source_id;
          RETURN true;
        END $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION auto_enable_personal_source(uuid,uuid,uuid,timestamptz) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auto_enable_personal_source(uuid,uuid,uuid,timestamptz) "
        "TO srbg_worker_role"
    )


def _seed_topics_and_score_queue() -> None:
    bind = op.get_bind()
    for code, name, keywords in TOPICS:
        bind.execute(
            sa.text(
                "INSERT INTO discovery_topic(id,code,name,keywords,excluded_terms,focus_regions,"
                "enabled,version,created_at,updated_at) VALUES(CAST(:id AS uuid),:code,:name,"
                "CAST(:keywords AS varchar(100)[]),ARRAY[]::varchar(100)[],"
                "ARRAY[]::varchar(100)[],true,1,now(),now())"
            ),
            {"id": str(uuid7()), "code": code, "name": name, "keywords": keywords},
        )
    for source_id in bind.execute(sa.text("SELECT id FROM source ORDER BY id")).scalars():
        bind.execute(
            sa.text(
                "INSERT INTO source_auto_score_run(id,source_id,status,reason,next_attempt_at,"
                "created_at,updated_at) VALUES(CAST(:id AS uuid),:source_id,'QUEUED',"
                "'EXISTING_SOURCE',now(),now(),now())"
            ),
            {"id": str(uuid7()), "source_id": source_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    materialized = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM discovery_occurrence) OR "
            "EXISTS(SELECT 1 FROM source_auto_score_snapshot) OR "
            "EXISTS(SELECT 1 FROM discovery_topic_event) OR "
            "EXISTS(SELECT 1 FROM personal_discovery_setting_event) OR "
            "EXISTS(SELECT 1 FROM personal_probe_daily_ledger WHERE used_count>0) OR "
            "EXISTS(SELECT 1 FROM personal_auto_enable_daily_ledger WHERE used_count>0)"
        )
    ).scalar_one()
    if materialized:
        raise RuntimeError("0025_DOWNGRADE_BLOCKED: personal discovery facts exist")
    op.execute("DELETE FROM source_auto_score_run")
    op.execute(
        "DROP FUNCTION IF EXISTS auto_enable_personal_source(uuid,uuid,uuid,timestamptz)"
    )
    for function in (
        "reserve_personal_auto_enable_budget",
        "reserve_personal_probe_budget",
        "personal_discovery_local_date",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}(timestamptz)")
    op.drop_constraint("ck_source_key_activity_event_type", "source_key_activity_event", type_="check")
    op.create_check_constraint(
        "ck_source_key_activity_event_type",
        "source_key_activity_event",
        "event_type IN ('MANUAL_DISABLED','MANUAL_ENABLED','DISPLAY_NAME_CHANGED')",
    )
    for table in (
        "source_auto_score_snapshot",
        "source_auto_score_run",
        "personal_auto_enable_daily_ledger",
        "personal_probe_daily_ledger",
        "discovery_occurrence",
        "personal_discovery_setting_event",
        "discovery_topic_event",
        "discovery_topic",
    ):
        op.drop_table(table)
