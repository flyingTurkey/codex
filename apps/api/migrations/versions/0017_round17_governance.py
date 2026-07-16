"""Round 17 bounded two-person source-governance cohort.

Revision ID: 0017_round17_governance
Revises: 0016_scheduling_health_replay
"""

# SQL DDL is intentionally kept intact for migration evidence review.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_round17_governance"
down_revision: str | Sequence[str] | None = "0016_scheduling_health_replay"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROUND17_GOVERNANCE_SCHEME = "R17_TWO_PERSON_MAKER_CHECKER_V1"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _create_scheme_assignment()
    _create_round17_maker_guard()
    _wrap_governance_boundaries()
    _configure_permissions()


def _create_scheme_assignment() -> None:
    op.create_table(
        "source_governance_scheme_assignment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("scheme", sa.String(50), nullable=False),
        sa.Column("cohort_key", sa.String(80), nullable=False),
        sa.Column("assigned_by", _uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(200), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scheme = 'R17_TWO_PERSON_MAKER_CHECKER_V1'",
            name="ck_source_governance_scheme_round17",
        ),
        sa.CheckConstraint(
            r"cohort_key ~ '^r17-sources-v[0-9]+\.[0-9]+$'",
            name="ck_source_governance_cohort_key",
        ),
        sa.CheckConstraint(
            "length(reason) BETWEEN 8 AND 500 AND reason !~ '[[:cntrl:]]'",
            name="ck_source_governance_scheme_reason",
        ),
        sa.CheckConstraint(
            "length(request_id) BETWEEN 1 AND 200 AND request_id !~ '[[:cntrl:]]'",
            name="ck_source_governance_scheme_request_id",
        ),
    )
    op.execute(
        """
        CREATE TRIGGER trg_source_governance_scheme_assignment_immutable
        BEFORE UPDATE OR DELETE ON source_governance_scheme_assignment
        FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_v2_governance_scheme(p_source_id uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT COALESCE(
            (SELECT assignment.scheme
               FROM source_governance_scheme_assignment assignment
              WHERE assignment.source_id=p_source_id),
            'FOUR_PERSON_SEPARATION_V1'
          )
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION assign_round17_two_person_governance(
          p_assignment_id uuid, p_source_id uuid, p_cohort_key text,
          p_actor_id uuid, p_reason text, p_request_id text, p_audit_id uuid,
          p_assigned_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_policy_id uuid;
          v_config_id uuid;
          v_trial_id uuid;
        BEGIN
          IF substring(p_assignment_id::text,15,1)<>'7'
             OR p_cohort_key !~ '^r17-sources-v[0-9]+\.[0-9]+$'
             OR source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true
             OR length(p_request_id) NOT BETWEEN 1 AND 200
             OR p_request_id ~ '[[:cntrl:]]' THEN
            RAISE EXCEPTION 'round17 governance assignment is invalid';
          END IF;
          SELECT s.lifecycle_state,s.current_policy_version_id,
                 s.current_connector_config_version_id,s.current_trial_run_id
            INTO v_state,v_policy_id,v_config_id,v_trial_id
            FROM source s
           WHERE s.id=p_source_id
             AND NOT EXISTS (
               SELECT 1 FROM source_governance_scheme_assignment assignment
                WHERE assignment.source_id=s.id
             )
             AND NOT EXISTS (
               SELECT 1 FROM source_governance_decision decision
                WHERE decision.source_id=s.id
             )
           FOR UPDATE OF s;
          IF NOT FOUND OR v_state NOT IN ('CANDIDATE','COMPLIANCE_REVIEW') THEN
            RAISE EXCEPTION 'round17 governance must be assigned before governance decisions';
          END IF;
          IF round17_source_actor_is_maker(
               p_source_id,v_policy_id,v_config_id,v_trial_id,p_actor_id
             ) THEN
            RAISE EXCEPTION 'a source maker cannot assign its governance scheme';
          END IF;
          INSERT INTO source_governance_scheme_assignment (
            id,source_id,scheme,cohort_key,assigned_by,reason,request_id,created_at
          ) VALUES (
            p_assignment_id,p_source_id,'R17_TWO_PERSON_MAKER_CHECKER_V1',
            p_cohort_key,p_actor_id,p_reason,p_request_id,p_assigned_at
          );
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_GOVERNANCE_SCHEME_ASSIGNED',p_actor_id,
            'SOURCE',p_source_id,NULL,
            jsonb_build_object(
              'governance_scheme','R17_TWO_PERSON_MAKER_CHECKER_V1',
              'cohort_key',p_cohort_key,'assignment_id',p_assignment_id
            ),p_reason,p_request_id,p_assigned_at
          );
          RETURN p_assignment_id;
        END $$
        """
    )


def _create_round17_maker_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION round17_source_actor_is_maker(
          p_source_id uuid, p_policy_id uuid, p_config_id uuid,
          p_trial_id uuid, p_actor_id uuid
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT p_actor_id IS NULL OR EXISTS (
            SELECT 1
              FROM source s
             WHERE s.id=p_source_id
               AND (
                 p_actor_id=s.registered_by
                 OR p_actor_id=s.governance_owner_id
                 OR EXISTS (
                   SELECT 1 FROM source_policy_version p
                    WHERE p.source_id=s.id AND p.submitted_by=p_actor_id
                      AND (p_policy_id IS NULL OR p.id=p_policy_id)
                 )
                 OR EXISTS (
                   SELECT 1 FROM connector_config_version c
                    WHERE c.source_id=s.id AND c.created_by=p_actor_id
                      AND (p_config_id IS NULL OR c.id=p_config_id)
                 )
                 OR EXISTS (
                   SELECT 1 FROM source_trial_run r
                    WHERE r.source_id=s.id AND r.requested_by=p_actor_id
                      AND (p_trial_id IS NULL OR r.id=p_trial_id)
                 )
                 OR EXISTS (
                   SELECT 1
                     FROM fetch_schedule schedule
                     JOIN audit_log audit
                       ON audit.target_type='fetch_schedule'
                      AND audit.target_id=schedule.id
                      AND audit.event_type='FETCH_SCHEDULE_UPDATED'
                    WHERE schedule.source_id=s.id AND audit.actor_id=p_actor_id
                 )
               )
          )
        $$
        """
    )


def _wrap_governance_boundaries() -> None:
    op.execute(
        """
        ALTER FUNCTION decide_source_policy_version(
          uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz
        ) RENAME TO decide_source_policy_version_round15
        """
    )
    op.execute(
        """
        ALTER FUNCTION start_source_trial_run(
          uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz
        ) RENAME TO start_source_trial_run_round15
        """
    )
    op.execute(
        """
        ALTER FUNCTION approve_source_production(
          uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz
        ) RENAME TO approve_source_production_round15
        """
    )
    op.execute(
        """
        CREATE FUNCTION decide_source_policy_version(
          p_source_id uuid, p_policy_id uuid, p_decision_id uuid, p_outcome text,
          p_actor_id uuid, p_reason text, p_request_id text, p_audit_id uuid,
          p_decided_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_submitter uuid;
          v_valid_until timestamptz;
          v_state text;
        BEGIN
          IF source_v2_governance_scheme(p_source_id)
               <> 'R17_TWO_PERSON_MAKER_CHECKER_V1' THEN
            RETURN decide_source_policy_version_round15(
              p_source_id,p_policy_id,p_decision_id,p_outcome,p_actor_id,
              p_reason,p_request_id,p_audit_id,p_decided_at
            );
          END IF;
          SELECT p.submitted_by,p.valid_until,s.lifecycle_state
            INTO v_submitter,v_valid_until,v_state
            FROM source_policy_version p JOIN source s ON s.id=p.source_id
           WHERE p.id=p_policy_id AND p.source_id=p_source_id
             AND p.valid_from <= p_decided_at AND p.valid_until > p_decided_at
           FOR UPDATE OF s;
          IF NOT FOUND THEN RAISE EXCEPTION 'current source policy does not exist'; END IF;
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          IF v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not accepting policy decisions';
          END IF;
          IF p_outcome NOT IN ('APPROVED','REJECTED') THEN
            RAISE EXCEPTION 'source policy decision is invalid';
          END IF;
          IF round17_source_actor_is_maker(
               p_source_id,p_policy_id,NULL,NULL,p_actor_id
             ) THEN
            RAISE EXCEPTION 'source policy decision violates maker checker duties';
          END IF;
          IF NOT EXISTS (
               SELECT 1 FROM source_governance_scheme_assignment assignment
                WHERE assignment.source_id=p_source_id
                  AND assignment.assigned_by=p_actor_id
             ) THEN
            RAISE EXCEPTION 'round17 governance checker is not assigned';
          END IF;
          INSERT INTO source_governance_decision (
            id,source_id,decision_type,outcome,policy_version_id,
            submitted_by,decided_by,reason,valid_until,created_at
          ) VALUES (
            p_decision_id,p_source_id,'COMPLIANCE',p_outcome,p_policy_id,
            v_submitter,p_actor_id,p_reason,v_valid_until,p_decided_at
          );
          IF p_outcome='APPROVED' THEN
            UPDATE source SET current_policy_version_id=p_policy_id,
              updated_at=p_decided_at WHERE id=p_source_id;
          END IF;
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_POLICY_' || p_outcome,p_actor_id,
            'SOURCE_POLICY_VERSION',p_policy_id,
            jsonb_build_object('status','PENDING_REVIEW'),
            jsonb_build_object('decision',p_outcome,'decision_id',p_decision_id),
            p_reason,p_request_id,p_decided_at
          );
          RETURN p_decision_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION start_source_trial_run(
          p_source_id uuid, p_trial_id uuid, p_kind text, p_policy_id uuid,
          p_config_id uuid, p_decision_id uuid, p_actor_id uuid, p_reason text,
          p_request_id text, p_event_id uuid, p_audit_id uuid,
          p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_config_submitter uuid;
          v_requested_by uuid;
        BEGIN
          IF source_v2_governance_scheme(p_source_id)
               <> 'R17_TWO_PERSON_MAKER_CHECKER_V1'
             OR p_kind <> 'LIVE_TRIAL' THEN
            RETURN start_source_trial_run_round15(
              p_source_id,p_trial_id,p_kind,p_policy_id,p_config_id,p_decision_id,
              p_actor_id,p_reason,p_request_id,p_event_id,p_audit_id,p_created_at
            );
          END IF;
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          SELECT s.lifecycle_state,c.created_by
            INTO v_state,v_config_submitter
            FROM source s
            JOIN source_policy_version p ON p.id=s.current_policy_version_id
            JOIN connector_config_version c
              ON c.id=s.current_connector_config_version_id
             AND c.source_id=s.id AND c.policy_version_id=p.id
            JOIN LATERAL (
              SELECT d.outcome,d.valid_until
                FROM source_governance_decision d
               WHERE d.source_id=s.id AND d.policy_version_id=p.id
                 AND d.decision_type='COMPLIANCE'
               ORDER BY d.created_at DESC,d.id DESC LIMIT 1
            ) compliance ON true
           WHERE s.id=p_source_id AND p.id=p_policy_id AND c.id=p_config_id
             AND p.source_id=s.id AND c.source_id=s.id
             AND p.valid_from <= p_created_at AND p.valid_until > p_created_at
             AND c.validation_status='VALID'
             AND s.governance_owner_id IS NOT NULL
             AND compliance.outcome='APPROVED'
             AND (compliance.valid_until IS NULL OR compliance.valid_until > p_created_at)
             AND source_v2_policy_compliance_approved(
                   s.id,p.id,p_created_at
                 ) IS TRUE
           FOR UPDATE OF s;
          IF NOT FOUND OR v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not ready for trial';
          END IF;
          IF v_state='TRIAL' AND EXISTS (
               SELECT 1 FROM source current_source
               JOIN source_trial_run current_run
                 ON current_run.id=current_source.current_trial_run_id
               LEFT JOIN source_trial_run_result current_result
                 ON current_result.trial_run_id=current_run.id
              WHERE current_source.id=p_source_id
                AND current_result.trial_run_id IS NULL
             ) THEN
            RAISE EXCEPTION 'current source trial is still pending';
          END IF;
          IF round17_source_actor_is_maker(
               p_source_id,p_policy_id,p_config_id,NULL,p_actor_id
             ) THEN
            RAISE EXCEPTION 'live trial authorization violates maker checker duties';
          END IF;
          IF NOT EXISTS (
               SELECT 1 FROM source_governance_scheme_assignment assignment
                WHERE assignment.source_id=p_source_id
                  AND assignment.assigned_by=p_actor_id
             ) THEN
            RAISE EXCEPTION 'round17 governance checker is not assigned';
          END IF;
          v_requested_by := v_config_submitter;
          INSERT INTO source_governance_decision (
            id,source_id,decision_type,outcome,policy_version_id,
            connector_config_version_id,submitted_by,decided_by,reason,
            valid_until,created_at
          ) VALUES (
            p_decision_id,p_source_id,'LIVE_TRIAL_AUTHORIZATION','APPROVED',
            p_policy_id,p_config_id,v_config_submitter,p_actor_id,p_reason,
            p_created_at + interval '7 days',p_created_at
          );
          INSERT INTO source_trial_run (
            id,source_id,kind,execution_domain,policy_version_id,
            connector_config_version_id,authorization_decision_id,requested_by,
            request_reason,created_at
          ) VALUES (
            p_trial_id,p_source_id,'LIVE_TRIAL','TRIAL',p_policy_id,
            p_config_id,p_decision_id,v_requested_by,p_reason,p_created_at
          );
          UPDATE source SET lifecycle_state='TRIAL',trial_kind='LIVE_TRIAL',
            current_trial_run_id=p_trial_id,updated_at=p_created_at
           WHERE id=p_source_id;
          INSERT INTO source_lifecycle_event (
            id,source_id,from_state,to_state,action,reason_code,reason,
            actor_id,policy_version_id,governance_decision_id,created_at
          ) VALUES (
            p_event_id,p_source_id,v_state,'TRIAL','START_LIVE_TRIAL',
            'TRIAL_AUTHORIZED',p_reason,p_actor_id,p_policy_id,p_decision_id,p_created_at
          );
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_TRIAL_STARTED',p_actor_id,'SOURCE_TRIAL_RUN',
            p_trial_id,jsonb_build_object('lifecycle_state',v_state),
            jsonb_build_object(
              'lifecycle_state','TRIAL','trial_kind','LIVE_TRIAL',
              'governance_decision_id',p_decision_id
            ),p_reason,p_request_id,p_created_at
          );
          RETURN p_trial_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION approve_source_production(
          p_source_id uuid, p_policy_id uuid, p_config_id uuid, p_trial_id uuid,
          p_decision_id uuid, p_actor_id uuid, p_reason text, p_request_id text,
          p_event_id uuid, p_audit_id uuid, p_approved_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_trial_requester uuid;
          v_valid_until timestamptz;
        BEGIN
          IF source_v2_governance_scheme(p_source_id)
               <> 'R17_TWO_PERSON_MAKER_CHECKER_V1' THEN
            RETURN approve_source_production_round15(
              p_source_id,p_policy_id,p_config_id,p_trial_id,p_decision_id,
              p_actor_id,p_reason,p_request_id,p_event_id,p_audit_id,p_approved_at
            );
          END IF;
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          SELECT s.lifecycle_state,r.requested_by,p.valid_until
            INTO v_state,v_trial_requester,v_valid_until
            FROM source s
            JOIN source_policy_version p ON p.id=s.current_policy_version_id
            JOIN connector_config_version c
              ON c.id=s.current_connector_config_version_id
             AND c.source_id=s.id AND c.policy_version_id=p.id
            JOIN source_trial_run r ON r.id=s.current_trial_run_id
            JOIN source_trial_run_result rr ON rr.trial_run_id=r.id
            JOIN LATERAL (
              SELECT d.outcome,d.valid_until
                FROM source_governance_decision d
               WHERE d.source_id=s.id AND d.policy_version_id=p.id
                 AND d.decision_type='COMPLIANCE'
               ORDER BY d.created_at DESC,d.id DESC LIMIT 1
            ) compliance ON compliance.outcome='APPROVED'
                         AND (compliance.valid_until IS NULL OR compliance.valid_until > p_approved_at)
            JOIN source_governance_decision auth_decision
              ON auth_decision.id=r.authorization_decision_id
             AND auth_decision.source_id=s.id
             AND auth_decision.decision_type='LIVE_TRIAL_AUTHORIZATION'
             AND auth_decision.outcome='APPROVED'
             AND (auth_decision.valid_until IS NULL OR auth_decision.valid_until > p_approved_at)
           WHERE s.id=p_source_id AND p.id=p_policy_id AND c.id=p_config_id
             AND r.id=p_trial_id AND p.source_id=s.id AND c.source_id=s.id
             AND r.source_id=s.id AND r.policy_version_id=p.id
             AND r.connector_config_version_id=c.id AND r.kind='LIVE_TRIAL'
             AND rr.status='SUCCEEDED' AND p.valid_from <= p_approved_at
             AND p.valid_until > p_approved_at AND c.validation_status='VALID'
             AND s.governance_owner_id IS NOT NULL
             AND source_v2_policy_compliance_approved(
                   s.id,p.id,p_approved_at
                 ) IS TRUE
           FOR UPDATE OF s;
          IF NOT FOUND OR v_state<>'TRIAL' THEN
            RAISE EXCEPTION 'source production evidence is incomplete or expired';
          END IF;
          IF round17_source_actor_is_maker(
               p_source_id,p_policy_id,p_config_id,p_trial_id,p_actor_id
             ) THEN
            RAISE EXCEPTION 'production approval violates maker checker duties';
          END IF;
          IF NOT EXISTS (
               SELECT 1 FROM source_governance_scheme_assignment assignment
                WHERE assignment.source_id=p_source_id
                  AND assignment.assigned_by=p_actor_id
             ) THEN
            RAISE EXCEPTION 'round17 governance checker is not assigned';
          END IF;
          INSERT INTO source_governance_decision (
            id,source_id,decision_type,outcome,policy_version_id,
            connector_config_version_id,trial_run_id,submitted_by,decided_by,
            reason,valid_until,created_at
          ) VALUES (
            p_decision_id,p_source_id,'PRODUCTION_APPROVAL','APPROVED',
            p_policy_id,p_config_id,p_trial_id,v_trial_requester,p_actor_id,
            p_reason,v_valid_until,p_approved_at
          );
          UPDATE source SET lifecycle_state='ACTIVE',trial_kind=NULL,
            updated_at=p_approved_at WHERE id=p_source_id;
          INSERT INTO source_lifecycle_event (
            id,source_id,from_state,to_state,action,reason_code,reason,
            actor_id,policy_version_id,governance_decision_id,created_at
          ) VALUES (
            p_event_id,p_source_id,v_state,'ACTIVE','APPROVE_PRODUCTION',
            'PRODUCTION_APPROVED',p_reason,p_actor_id,p_policy_id,
            p_decision_id,p_approved_at
          );
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_PRODUCTION_APPROVED',p_actor_id,'SOURCE',
            p_source_id,jsonb_build_object('lifecycle_state',v_state),
            jsonb_build_object(
              'lifecycle_state','ACTIVE','governance_decision_id',p_decision_id
            ),p_reason,p_request_id,p_approved_at
          );
          RETURN p_decision_id;
        END $$
        """
    )


def _configure_permissions() -> None:
    assignment_signature = (
        "assign_round17_two_person_governance(uuid,uuid,text,uuid,text,text,uuid,timestamptz)"
    )
    scheme_signature = "source_v2_governance_scheme(uuid)"
    maker_signature = "round17_source_actor_is_maker(uuid,uuid,uuid,uuid,uuid)"
    wrapper_signatures = (
        "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    )
    legacy_signatures = (
        "decide_source_policy_version_round15(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "start_source_trial_run_round15(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "approve_source_production_round15(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    )
    op.execute("REVOKE ALL ON source_governance_scheme_assignment FROM PUBLIC")
    op.execute(
        "REVOKE INSERT,UPDATE,DELETE ON source_governance_scheme_assignment FROM "
        "srbg_runtime,srbg_api_role,srbg_worker_role,srbg_publication_writer,srbg_model_role,"
        "srbg_source_governance_writer"
    )
    op.execute(
        "GRANT SELECT ON source_governance_scheme_assignment TO "
        "srbg_runtime,srbg_api_role,srbg_worker_role,srbg_publication_writer,"
        "srbg_source_governance_writer"
    )
    for signature in (assignment_signature, scheme_signature, maker_signature, *wrapper_signatures):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    for signature in legacy_signatures:
        op.execute(
            f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,srbg_api_role,"
            "srbg_source_governance_writer"
        )
    op.execute(f"GRANT EXECUTE ON FUNCTION {assignment_signature} TO srbg_api_role")
    for signature in wrapper_signatures:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")


def downgrade() -> None:
    _guard_round17_governance_downgrade()
    _restore_governance_boundaries()
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "assign_round17_two_person_governance(uuid,uuid,text,uuid,text,text,uuid,timestamptz)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS round17_source_actor_is_maker(uuid,uuid,uuid,uuid,uuid)"
    )
    op.execute("DROP FUNCTION IF EXISTS source_v2_governance_scheme(uuid)")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_source_governance_scheme_assignment_immutable "
        "ON source_governance_scheme_assignment"
    )
    op.drop_table("source_governance_scheme_assignment")


def _guard_round17_governance_downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM source_governance_scheme_assignment) THEN
            RAISE EXCEPTION
              'ROUND17_GOVERNANCE_DOWNGRADE_BLOCKED: governance assignments exist';
          END IF;
        END $$
        """
    )


def _restore_governance_boundaries() -> None:
    wrapper_signatures = (
        "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    )
    for signature in wrapper_signatures:
        op.execute(f"DROP FUNCTION {signature}")
    op.execute(
        """
        ALTER FUNCTION decide_source_policy_version_round15(
          uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz
        ) RENAME TO decide_source_policy_version
        """
    )
    op.execute(
        """
        ALTER FUNCTION start_source_trial_run_round15(
          uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz
        ) RENAME TO start_source_trial_run
        """
    )
    op.execute(
        """
        ALTER FUNCTION approve_source_production_round15(
          uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz
        ) RENAME TO approve_source_production
        """
    )
    restored_signatures = (
        "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    )
    for signature in restored_signatures:
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")
