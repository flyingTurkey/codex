"""PERS-10 retire enterprise governance into a verified read-only archive.

Revision ID: 0029_legacy_governance_retirement
Revises: 0028_automatic_relationships
"""

# The relation names below are a closed, reviewed migration inventory.
# ruff: noqa: S608

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_legacy_governance_retirement"
down_revision: str | Sequence[str] | None = "0028_automatic_relationships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ARCHIVE_SCHEMA = "legacy_governance_archive"
LEGACY_DATABASE_ROLES: tuple[str, ...] = ("srbg_admin_role", "srbg_model_role")
RETIRED_CORE_TRIGGERS: tuple[tuple[str, str, str], ...] = (
    (
        "event",
        "trg_event_pending_insert",
        "CREATE TRIGGER trg_event_pending_insert BEFORE INSERT ON public.event "
        "FOR EACH ROW EXECUTE FUNCTION enforce_pending_event_insert()",
    ),
    (
        "source",
        "trg_round17_source_authority_change",
        "CREATE TRIGGER trg_round17_source_authority_change AFTER UPDATE ON public.source "
        "FOR EACH ROW EXECUTE FUNCTION pause_round17_segments_on_source_change()",
    ),
    (
        "source",
        "trg_source_automation_lifecycle_authority",
        "CREATE TRIGGER trg_source_automation_lifecycle_authority BEFORE UPDATE OF "
        "lifecycle_state ON public.source FOR EACH ROW EXECUTE FUNCTION "
        "enforce_source_automation_lifecycle_authority()",
    ),
    (
        "fetch_schedule",
        "trg_round17_schedule_change",
        "CREATE TRIGGER trg_round17_schedule_change AFTER UPDATE ON public.fetch_schedule "
        "FOR EACH ROW EXECUTE FUNCTION pause_round17_segments_on_schedule_change()",
    ),
    (
        "fetch_run",
        "trg_fetch_run_bind_round17",
        "CREATE TRIGGER trg_fetch_run_bind_round17 BEFORE INSERT ON public.fetch_run "
        "FOR EACH ROW EXECUTE FUNCTION bind_round17_fetch_run()",
    ),
    (
        "source_anomaly",
        "trg_round17_source_anomaly",
        "CREATE TRIGGER trg_round17_source_anomaly AFTER INSERT ON public.source_anomaly "
        "FOR EACH ROW EXECUTE FUNCTION pause_round17_segments_on_anomaly()",
    ),
    (
        "document",
        "trg_document_reject_closed_trial_current",
        "CREATE TRIGGER trg_document_reject_closed_trial_current BEFORE INSERT OR UPDATE OF "
        "current_version_id ON public.document FOR EACH ROW EXECUTE FUNCTION "
        "reject_closed_trial_version_as_current()",
    ),
    (
        "document_version",
        "trg_document_version_execution_domain",
        "CREATE TRIGGER trg_document_version_execution_domain BEFORE INSERT ON "
        "public.document_version FOR EACH ROW EXECUTE FUNCTION "
        "enforce_document_version_execution_domain()",
    ),
    (
        "document_version_state_event",
        "trg_document_version_reject_closed_trial_ready",
        "CREATE TRIGGER trg_document_version_reject_closed_trial_ready BEFORE INSERT ON "
        "public.document_version_state_event FOR EACH ROW EXECUTE FUNCTION "
        "reject_closed_trial_version_promotion()",
    ),
)
# Security-review evidence: the rendered statements are
# ``REVOKE ALL ON SCHEMA legacy_governance_archive FROM PUBLIC`` and, after a
# verified downgrade, ``DROP SCHEMA legacy_governance_archive``.

# Each relation has a single UUID primary key named ``id``.  Shared/core fact
# relations are deliberately absent: only enterprise governance and manual
# resolution records are retired.
LEGACY_RELATIONS: tuple[str, ...] = (
    "source_candidate_occurrence",
    "source_qualification_capture",
    "source_qualification_bundle",
    "source_candidate_decision",
    "source_qualification_run",
    "source_candidate",
    "source_governance_scheme_assignment",
    "source_trial_run_result",
    "source_trial_rejected_raw_attempt",
    "source_trial_run",
    "source_governance_decision",
    "source_authority_assessment",
    "source_independence_assessment",
    "source_policy_version",
    "connector_config_version",
    "review_decision",
    "security_review_decision",
    "ai_claim_review_decision",
    "claim_field_decision",
    "claim_conflict_decision",
    "review_task",
    "duplicate_candidate",
    "duplicate_decision",
    "event_item_candidate",
    "event_item_decision",
    "event_relation_candidate",
    "event_relation_decision",
    "document_relation_candidate",
    "document_relation_decision",
    "regulation_status_candidate",
    "regulation_status_decision",
    "paper_duplicate_candidate",
    "item_relation_candidate",
    "cluster_decision",
    "event_identity_change_decision",
    "product_normalization_candidate",
    "round17_staff_binding",
    "round17_eventization_readiness",
    "round17_pilot_window_source",
    "round17_pilot_window",
    "round17_gold_release",
    "round17_gold_arbitration",
    "round17_gold_annotation",
    "round17_gold_assignment",
    "round17_gold_task",
    "round17_operator_work_correction",
    "round17_operator_work_session",
    "round17_operator_task",
    "round17_metric_snapshot",
    "round17_signed_approval",
    "round17_reference_annotation",
)


def _execute(statement: str, parameters: dict[str, object] | None = None) -> None:
    op.get_bind().execute(sa.text(statement), parameters or {})


def _assert_replacement_complete() -> None:
    bind = op.get_bind()
    incomplete = bind.execute(
        sa.text(
            """
            SELECT EXISTS(
              SELECT 1 FROM source s
               WHERE s.desired_enabled=true AND s.manual_disabled_at IS NULL
                 AND NOT EXISTS(
                   SELECT 1 FROM source_stream stream
                   JOIN stream_config_version config
                     ON config.stream_id=stream.id
                    AND config.config_sha256=stream.config_sha256
                  WHERE stream.source_id=s.id AND stream.status='READY'
                 )
            ) OR EXISTS(
              SELECT 1 FROM fetch_schedule
               WHERE status='ACTIVE' AND authority_mode='LEGACY_GOVERNED'
            )
            """
        )
    ).scalar_one()
    if incomplete:
        raise RuntimeError("PERS10_REPLACEMENT_INCOMPLETE")


def _create_archive() -> None:
    _execute("SET LOCAL TIME ZONE 'UTC'")
    _execute(f"CREATE SCHEMA {ARCHIVE_SCHEMA}")
    _execute(
        f"""
        CREATE TABLE {ARCHIVE_SCHEMA}.legacy_governance_archive_record(
          entity_type text NOT NULL,
          original_id text NOT NULL,
          source_id uuid,
          normalized_payload jsonb NOT NULL,
          row_sha256 text NOT NULL,
          archived_at timestamptz NOT NULL,
          PRIMARY KEY(entity_type,original_id),
          CONSTRAINT ck_legacy_archive_row_hash
            CHECK(row_sha256 ~ '^[0-9a-f]{{64}}$')
        )
        """
    )
    _execute(
        f"""
        CREATE TABLE {ARCHIVE_SCHEMA}.legacy_governance_archive_manifest(
          entity_type text PRIMARY KEY,
          source_relation text NOT NULL,
          original_count bigint NOT NULL,
          archive_count bigint NOT NULL,
          aggregate_sha256 text NOT NULL,
          migration_version text NOT NULL,
          archived_at timestamptz NOT NULL,
          CONSTRAINT ck_legacy_archive_manifest_counts
            CHECK(original_count >= 0 AND archive_count >= 0),
          CONSTRAINT ck_legacy_archive_manifest_hash
            CHECK(aggregate_sha256 ~ '^[0-9a-f]{{64}}$')
        )
        """
    )
    _execute(
        f"REVOKE ALL ON SCHEMA {ARCHIVE_SCHEMA} FROM PUBLIC, srbg_runtime, "
        "srbg_api_role, srbg_worker_role, srbg_publication_writer, "
        "srbg_projection_reader, srbg_admin_role, srbg_model_role"
    )
    _execute(
        f"REVOKE ALL ON ALL TABLES IN SCHEMA {ARCHIVE_SCHEMA} FROM PUBLIC, "
        "srbg_runtime, srbg_api_role, srbg_worker_role, srbg_publication_writer, "
        "srbg_projection_reader, srbg_admin_role, srbg_model_role"
    )


def _source_expression(relation: str) -> str:
    bind = op.get_bind()
    columns = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:name"
            ),
            {"name": relation},
        )
    }
    if "source_id" in columns:
        return "t.source_id"
    if "prepared_source_id" in columns:
        return "t.prepared_source_id"
    if "candidate_id" in columns and relation != "source_candidate":
        return "(SELECT c.source_id FROM public.source_candidate c WHERE c.id=t.candidate_id)"
    return "NULL::uuid"


def _primary_key_expression(relation: str) -> str:
    columns = list(
        op.get_bind().execute(
            sa.text(
                """
                SELECT attribute.attname
                  FROM pg_index index_row
                  JOIN pg_class relation ON relation.oid=index_row.indrelid
                  JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
                  JOIN unnest(index_row.indkey) WITH ORDINALITY key(attnum,position) ON true
                  JOIN pg_attribute attribute
                    ON attribute.attrelid=relation.oid AND attribute.attnum=key.attnum
                 WHERE namespace.nspname='public' AND relation.relname=:name
                   AND index_row.indisprimary
                 ORDER BY key.position
                """
            ),
            {"name": relation},
        ).scalars()
    )
    if not columns:
        raise RuntimeError(f"PERS10_ARCHIVE_CORRUPT:{relation}:missing-primary-key")
    values = ",".join(f't."{column}"::text' for column in columns)
    return f"concat_ws('|',{values})"


def _archive_relation(relation: str, archived_at: object) -> None:
    source_expression = _source_expression(relation)
    original_id_expression = _primary_key_expression(relation)
    _execute(
        f"""
        INSERT INTO {ARCHIVE_SCHEMA}.legacy_governance_archive_record(
          entity_type,original_id,source_id,normalized_payload,row_sha256,archived_at
        )
        SELECT CAST(:entity AS text),{original_id_expression},{source_expression},to_jsonb(t),
               encode(digest(convert_to(jsonb_build_object(
                 'entity_type',CAST(:entity AS text),'original_id',{original_id_expression},
                 'source_id',{source_expression},'payload',to_jsonb(t)
               )::text,'UTF8'),'sha256'),'hex'),CAST(:archived_at AS timestamptz)
          FROM public.{relation} t
        """,
        {"entity": relation, "archived_at": archived_at},
    )
    _write_manifest(relation, f"public.{relation}", archived_at)


def _write_manifest(entity_type: str, source_relation: str, archived_at: object) -> None:
    original_count = op.get_bind().execute(
        sa.text(f"SELECT count(*) FROM {source_relation}")
    ).scalar_one()
    archive_count = op.get_bind().execute(
        sa.text(
            f"SELECT count(*) FROM {ARCHIVE_SCHEMA}.legacy_governance_archive_record "
            "WHERE entity_type=:entity"
        ),
        {"entity": entity_type},
    ).scalar_one()
    if original_count != archive_count:
        raise RuntimeError(f"PERS10_ARCHIVE_COUNT_MISMATCH:{entity_type}")
    aggregate = op.get_bind().execute(
        sa.text(
            f"""
            SELECT encode(digest(convert_to(
              CAST(:count AS bigint)::text || E'\n' || COALESCE(string_agg(
                original_id || ':' || row_sha256,E'\n' ORDER BY original_id
              ),''),'UTF8'),'sha256'),'hex')
              FROM {ARCHIVE_SCHEMA}.legacy_governance_archive_record
             WHERE entity_type=:entity
            """
        ),
        {"count": original_count, "entity": entity_type},
    ).scalar_one()
    _execute(
        f"""
        INSERT INTO {ARCHIVE_SCHEMA}.legacy_governance_archive_manifest(
          entity_type,source_relation,original_count,archive_count,
          aggregate_sha256,migration_version,archived_at
        ) VALUES(:entity,:relation,:original_count,:archive_count,:aggregate,
                 '0029_legacy_governance_retirement',:archived_at)
        """,
        {
            "entity": entity_type,
            "relation": source_relation,
            "original_count": original_count,
            "archive_count": archive_count,
            "aggregate": aggregate,
            "archived_at": archived_at,
        },
    )


def _archive_governance_metadata(archived_at: object) -> None:
    entity = "source_governance_metadata_audit"
    _execute(
        f"""
        INSERT INTO {ARCHIVE_SCHEMA}.legacy_governance_archive_record(
          entity_type,original_id,source_id,normalized_payload,row_sha256,archived_at
        )
        SELECT CAST(:entity AS text),a.id::text,a.target_id,to_jsonb(a),
               encode(digest(convert_to(jsonb_build_object(
                 'entity_type',CAST(:entity AS text),'original_id',a.id::text,
                 'source_id',a.target_id,'payload',to_jsonb(a)
               )::text,'UTF8'),'sha256'),'hex'),CAST(:archived_at AS timestamptz)
          FROM public.audit_log a
         WHERE a.event_type IN(
           'SOURCE_GOVERNANCE_METADATA_UPDATED','SOURCE_ASSESSMENTS_APPENDED'
         ) AND a.target_type='SOURCE'
        """,
        {"entity": entity, "archived_at": archived_at},
    )
    _write_manifest(
        entity,
        "(SELECT * FROM public.audit_log WHERE event_type IN "
        "('SOURCE_GOVERNANCE_METADATA_UPDATED','SOURCE_ASSESSMENTS_APPENDED') "
        "AND target_type='SOURCE') AS governance_audit",
        archived_at,
    )


def _archive_database_roles(archived_at: object) -> None:
    entity = "database_role"
    _execute(
        f"""
        INSERT INTO {ARCHIVE_SCHEMA}.legacy_governance_archive_record(
          entity_type,original_id,source_id,normalized_payload,row_sha256,archived_at
        )
        SELECT CAST(:entity AS text),role_row.rolname,NULL::uuid,payload.document,
               encode(digest(convert_to(jsonb_build_object(
                 'entity_type',CAST(:entity AS text),'original_id',role_row.rolname,
                 'source_id',NULL::uuid,'payload',payload.document
               )::text,'UTF8'),'sha256'),'hex'),CAST(:archived_at AS timestamptz)
          FROM pg_roles role_row
          CROSS JOIN LATERAL(
            SELECT jsonb_build_object(
              'rolname',role_row.rolname,
              'rolinherit',role_row.rolinherit,
              'rolconnlimit',role_row.rolconnlimit,
              'memberships',COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                  'role',parent.rolname,'admin_option',membership.admin_option
                ) ORDER BY parent.rolname)
                  FROM pg_auth_members membership
                  JOIN pg_roles parent ON parent.oid=membership.roleid
                 WHERE membership.member=role_row.oid
              ),'[]'::jsonb),
              'table_privileges',COALESCE((
                SELECT jsonb_agg(jsonb_build_object(
                  'schema',grant_row.table_schema,'relation',grant_row.table_name,
                  'privilege',grant_row.privilege_type,
                  'grantable',grant_row.is_grantable='YES'
                ) ORDER BY grant_row.table_schema,grant_row.table_name,
                           grant_row.privilege_type)
                  FROM information_schema.role_table_grants grant_row
                 WHERE grant_row.grantee=role_row.rolname
              ),'[]'::jsonb)
            ) AS document
          ) payload
         WHERE role_row.rolname = ANY(CAST(:roles AS text[]))
        """,
        {"entity": entity, "roles": list(LEGACY_DATABASE_ROLES), "archived_at": archived_at},
    )
    _write_manifest(
        entity,
        "(SELECT * FROM pg_roles WHERE rolname IN "
        "('srbg_admin_role','srbg_model_role')) AS legacy_roles",
        archived_at,
    )


def _retire_legacy_database_roles() -> None:
    for role in LEGACY_DATABASE_ROLES:
        _execute(f"DROP OWNED BY {role}")
        _execute(f"DROP ROLE {role}")


def _restore_legacy_database_roles() -> None:
    bind = op.get_bind()
    quote = bind.dialect.identifier_preparer.quote
    allowed_privileges = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
    }
    payloads = {
        row[0]: row[1]
        for row in bind.execute(
            sa.text(
                f"SELECT original_id,normalized_payload FROM {ARCHIVE_SCHEMA}."
                "legacy_governance_archive_record WHERE entity_type='database_role'"
            )
        )
    }
    if set(payloads) != set(LEGACY_DATABASE_ROLES):
        raise RuntimeError("PERS10_ARCHIVE_CORRUPT:database_role")
    for role in LEGACY_DATABASE_ROLES:
        document = payloads[role]
        if document.get("rolname") != role or document.get("rolinherit") is not True:
            raise RuntimeError("PERS10_ARCHIVE_CORRUPT:database_role")
        connection_limit = document.get("rolconnlimit")
        if not isinstance(connection_limit, int) or connection_limit < -1:
            raise RuntimeError("PERS10_ARCHIVE_CORRUPT:database_role")
        _execute(
            f"CREATE ROLE {quote(role)} NOLOGIN INHERIT NOSUPERUSER NOCREATEDB "
            f"NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {connection_limit}"
        )
    for role in LEGACY_DATABASE_ROLES:
        document = payloads[role]
        for membership in document.get("memberships", []):
            parent = membership.get("role")
            if not isinstance(parent, str) or parent in LEGACY_DATABASE_ROLES:
                raise RuntimeError("PERS10_ARCHIVE_CORRUPT:database_role_membership")
            suffix = " WITH ADMIN OPTION" if membership.get("admin_option") is True else ""
            _execute(f"GRANT {quote(parent)} TO {quote(role)}{suffix}")
        for grant in document.get("table_privileges", []):
            schema = grant.get("schema")
            relation = grant.get("relation")
            privilege = grant.get("privilege")
            if (
                schema != "public"
                or not isinstance(relation, str)
                or privilege not in allowed_privileges
            ):
                raise RuntimeError("PERS10_ARCHIVE_CORRUPT:database_role_grant")
            suffix = " WITH GRANT OPTION" if grant.get("grantable") is True else ""
            _execute(
                f"GRANT {privilege} ON TABLE {quote(schema)}.{quote(relation)} "
                f"TO {quote(role)}{suffix}"
            )
def _freeze_and_move_relation(relation: str) -> None:
    # Existing business triggers remain with the archived table but are disabled;
    # this preserves exact downgrade metadata without leaving active governance.
    trigger_names = list(
        op.get_bind().execute(
            sa.text(
                "SELECT tgname FROM pg_trigger WHERE tgrelid=CAST(:relation AS regclass) "
                "AND NOT tgisinternal"
            ),
            {"relation": f"public.{relation}"},
        ).scalars()
    )
    for trigger in trigger_names:
        _execute(f'ALTER TABLE public.{relation} DISABLE TRIGGER "{trigger}"')
    _execute(f"ALTER TABLE public.{relation} SET SCHEMA {ARCHIVE_SCHEMA}")
    _execute(
        f"""
        CREATE TRIGGER trg_pers10_archive_read_only
        BEFORE INSERT OR UPDATE OR DELETE ON {ARCHIVE_SCHEMA}.{relation}
        FOR EACH ROW EXECUTE FUNCTION {ARCHIVE_SCHEMA}.reject_archive_mutation()
        """
    )


def _install_archive_guard() -> None:
    _execute(
        f"""
        CREATE FUNCTION {ARCHIVE_SCHEMA}.reject_archive_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'PERS10_ARCHIVE_READ_ONLY';
        END $$
        """
    )
    for relation in (
        "legacy_governance_archive_record",
        "legacy_governance_archive_manifest",
    ):
        _execute(
            f"""
            CREATE TRIGGER trg_pers10_archive_read_only
            BEFORE INSERT OR UPDATE OR DELETE ON {ARCHIVE_SCHEMA}.{relation}
            FOR EACH ROW EXECUTE FUNCTION {ARCHIVE_SCHEMA}.reject_archive_mutation()
            """
        )


def _verify_archive() -> None:
    bind = op.get_bind()
    row_mismatch = bind.execute(
        sa.text(
            f"""
            SELECT EXISTS(
              SELECT 1 FROM {ARCHIVE_SCHEMA}.legacy_governance_archive_record r
               WHERE r.row_sha256 <> encode(digest(convert_to(jsonb_build_object(
                 'entity_type',r.entity_type,'original_id',r.original_id,
                 'source_id',r.source_id,'payload',r.normalized_payload
               )::text,'UTF8'),'sha256'),'hex')
            )
            """
        )
    ).scalar_one()
    if row_mismatch:
        raise RuntimeError("PERS10_ARCHIVE_HASH_MISMATCH")
    manifest_mismatch = bind.execute(
        sa.text(
            f"""
            SELECT EXISTS(
              SELECT 1 FROM {ARCHIVE_SCHEMA}.legacy_governance_archive_manifest m
              LEFT JOIN LATERAL(
                SELECT count(*) AS actual_count,
                       encode(digest(convert_to(
                         count(*)::text || E'\n' || COALESCE(string_agg(
                           r.original_id || ':' || r.row_sha256,E'\n'
                           ORDER BY r.original_id
                         ),''),'UTF8'),'sha256'),'hex') AS actual_hash
                  FROM {ARCHIVE_SCHEMA}.legacy_governance_archive_record r
                 WHERE r.entity_type=m.entity_type
              ) a ON true
             WHERE m.original_count<>m.archive_count
                OR m.archive_count<>a.actual_count
                OR m.aggregate_sha256<>a.actual_hash
                OR m.migration_version<>'0029_legacy_governance_retirement'
            )
            """
        )
    ).scalar_one()
    if manifest_mismatch:
        raise RuntimeError("PERS10_ARCHIVE_CORRUPT")


def _install_personal_claim_function() -> None:
    _execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              JOIN source_stream stream ON stream.id=schedule.source_stream_id
              JOIN stream_config_version config
                ON config.id=schedule.stream_config_version_id
               AND config.stream_id=stream.id
             WHERE schedule.authority_mode='PERSONAL_STREAM'
               AND schedule.status='ACTIVE' AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (schedule.circuit_state='CLOSED' OR
                    (schedule.circuit_state='OPEN' AND schedule.circuit_open_until<=p_now))
               AND source_row.desired_enabled=true
               AND source_row.manual_disabled_at IS NULL
               AND stream.source_id=source_row.id AND stream.status='READY'
               AND stream.config_sha256=config.config_sha256
               AND schedule.access_state='ACCESSIBLE'
             ORDER BY schedule.next_run_at,schedule.id
             LIMIT 1 FOR UPDATE OF schedule SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END,
                 self_heal_state=CASE WHEN schedule.circuit_state='OPEN'
                                      THEN 'HALF_OPEN_PROBE' ELSE schedule.self_heal_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )


def _install_pre_retirement_claim_function() -> None:
    """Restore the exact PERS-02 dual-authority scheduler on downgrade."""
    _execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              LEFT JOIN source_stream stream ON stream.id=schedule.source_stream_id
              LEFT JOIN stream_config_version stream_config
                ON stream_config.id=schedule.stream_config_version_id
              LEFT JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              LEFT JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE schedule.status='ACTIVE'
               AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (
                 schedule.circuit_state='CLOSED'
                 OR (schedule.circuit_state='OPEN' AND schedule.circuit_open_until<=p_now)
               )
               AND (
                 (
                   schedule.authority_mode='PERSONAL_STREAM'
                   AND source_row.desired_enabled=true
                   AND source_row.manual_disabled_at IS NULL
                   AND stream.source_id=source_row.id AND stream.status='READY'
                   AND stream.config_sha256=stream_config.config_sha256
                   AND stream_config.stream_id=stream.id
                   AND schedule.access_state='ACCESSIBLE'
                 ) OR (
                   schedule.authority_mode='LEGACY_GOVERNED'
                   AND source_row.lifecycle_state='ACTIVE'
                   AND source_policy_compliance_current(source_row.id,policy.id,p_now)
                   AND source_private_evidence_capture_allowed(policy.document)
                   AND config.validation_status='VALID'
                   AND EXISTS (
                     SELECT 1 FROM source_governance_decision decision
                      WHERE decision.source_id=source_row.id
                        AND decision.policy_version_id=policy.id
                        AND decision.connector_config_version_id=config.id
                        AND decision.trial_run_id=source_row.current_trial_run_id
                        AND decision.decision_type='PRODUCTION_APPROVAL'
                        AND decision.outcome='APPROVED'
                        AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
                   )
                 )
               )
             ORDER BY schedule.next_run_at,schedule.id
             LIMIT 1 FOR UPDATE OF schedule SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END,
                 self_heal_state=CASE WHEN schedule.circuit_state='OPEN'
                                      THEN 'HALF_OPEN_PROBE' ELSE schedule.self_heal_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )


def _set_personal_content_handoff(*, enabled: bool) -> None:
    definition = op.get_bind().execute(
        sa.text(
            "SELECT pg_get_functiondef("
            "'handoff_source_content_to_ai(uuid,uuid,timestamptz)'::regprocedure)"
        )
    ).scalar_one()
    old = "latest_state.state='READY'"
    new = "latest_state.state IN ('READY','SECURITY_PASSED')"
    candidates = (
        (old, new),
    ) if enabled else (
        (new, old),
        (
            "latest_state.state = ANY (ARRAY['READY'::character varying, "
            "'SECURITY_PASSED'::character varying]::text[])",
            old,
        ),
    )
    replacement = next(
        ((source, target) for source, target in candidates if source in definition), None
    )
    if replacement is None:
        raise RuntimeError("PERS10_CONTENT_HANDOFF_DEFINITION_UNEXPECTED")
    source, target = replacement
    _execute(definition.replace(source, target))


def upgrade() -> None:
    # The explicitly required revision identifier is longer than Alembic's
    # historical default VARCHAR(32); widen before Alembic records this head.
    _execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE varchar(64)")
    _assert_replacement_complete()
    # The personal profile scorer reads active discovery topics. This is a
    # necessary internal service grant, not an enterprise product role.
    _execute("GRANT SELECT ON public.discovery_topic TO srbg_worker_role")
    _execute("GRANT SELECT ON public.source_content_outbox TO srbg_worker_role")
    _execute("GRANT INSERT ON public.event_identity_binding TO srbg_worker_role")
    _execute(
        "GRANT SELECT ON public.automatic_evidence_acceptance, "
        "public.automatic_evidence_fact_state_event TO srbg_publication_writer"
    )
    _execute("GRANT UPDATE ON public.ai_judgment_version TO srbg_publication_writer")
    # Projection reads use a dedicated least-privilege login rather than the
    # general runtime role. Table SELECT alone is unusable without schema USAGE.
    _execute("GRANT USAGE ON SCHEMA public TO srbg_projection_reader")
    _create_archive()
    archived_at = op.get_bind().execute(sa.text("SELECT transaction_timestamp()")) .scalar_one()
    for relation in LEGACY_RELATIONS:
        _archive_relation(relation, archived_at)
    _archive_governance_metadata(archived_at)
    _archive_database_roles(archived_at)
    _verify_archive()
    _install_archive_guard()
    for relation in LEGACY_RELATIONS:
        _freeze_and_move_relation(relation)
    for relation, trigger_name, _ in RETIRED_CORE_TRIGGERS:
        _execute(f'DROP TRIGGER IF EXISTS "{trigger_name}" ON public.{relation}')
    _retire_legacy_database_roles()
    _install_personal_claim_function()
    _set_personal_content_handoff(enabled=True)


def downgrade() -> None:
    # PERS10_ARCHIVE_CORRUPT must be raised before any relation returns to public.
    _verify_archive()
    _execute("REVOKE UPDATE ON public.ai_judgment_version FROM srbg_publication_writer")
    _execute(
        "REVOKE SELECT ON public.automatic_evidence_acceptance, "
        "public.automatic_evidence_fact_state_event FROM srbg_publication_writer"
    )
    _execute("REVOKE INSERT ON public.event_identity_binding FROM srbg_worker_role")
    _set_personal_content_handoff(enabled=False)
    for relation in reversed(LEGACY_RELATIONS):
        _execute(
            f"DROP TRIGGER trg_pers10_archive_read_only ON {ARCHIVE_SCHEMA}.{relation}"
        )
        _execute(f"ALTER TABLE {ARCHIVE_SCHEMA}.{relation} SET SCHEMA public")
        trigger_names = list(
            op.get_bind().execute(
                sa.text(
                    "SELECT tgname FROM pg_trigger WHERE tgrelid=CAST(:relation AS regclass) "
                    "AND NOT tgisinternal AND tgname<>'trg_pers10_archive_read_only'"
                ),
                {"relation": f"public.{relation}"},
            ).scalars()
        )
        for trigger in trigger_names:
            _execute(f'ALTER TABLE public.{relation} ENABLE TRIGGER "{trigger}"')
    for _, _, trigger_ddl in RETIRED_CORE_TRIGGERS:
        _execute(trigger_ddl)
    _install_pre_retirement_claim_function()
    _restore_legacy_database_roles()
    _execute(
        f"DROP TRIGGER trg_pers10_archive_read_only ON "
        f"{ARCHIVE_SCHEMA}.legacy_governance_archive_manifest"
    )
    _execute(
        f"DROP TRIGGER trg_pers10_archive_read_only ON "
        f"{ARCHIVE_SCHEMA}.legacy_governance_archive_record"
    )
    _execute(f"DROP FUNCTION {ARCHIVE_SCHEMA}.reject_archive_mutation()")
    _execute(f"DROP TABLE {ARCHIVE_SCHEMA}.legacy_governance_archive_manifest")
    _execute(f"DROP TABLE {ARCHIVE_SCHEMA}.legacy_governance_archive_record")
    _execute(f"DROP SCHEMA {ARCHIVE_SCHEMA}")
    _execute("REVOKE USAGE ON SCHEMA public FROM srbg_projection_reader")
