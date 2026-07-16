"""PostgreSQL persistence for source admission and immutable document versions."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    ConnectorConfigVersionView,
    ConnectorDefinitionView,
    ConnectorType,
    CreateSourceRequest,
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
    RawObjectSummary,
    ScanStatus,
    SourceAssessmentSubmission,
    SourceAuthorityAssessment,
    SourceContentDomain,
    SourceCoverageCell,
    SourceCoverageMatrix,
    SourceGovernanceMetadataUpdate,
    SourceIndependenceAssessment,
    SourceIndustry,
    SourceLifecycleEventView,
    SourceLifecycleState,
    SourcePolicyDecisionOutcome,
    SourcePolicyV2Submission,
    SourcePolicyVersionView,
    SourceState,
    SourceTrialKind,
    SourceTrialQualitySummary,
    SourceTrialRunRequest,
    SourceTrialRunStatus,
    SourceTrialRunView,
    SourceType,
)

from srbg_api.document_vault.service import (
    AttachmentAttemptRecord,
    AttachmentRecord,
    FixtureRecord,
    RejectedRawRecord,
)
from srbg_api.identifiers import uuid7

ROUND17_TWO_PERSON_GOVERNANCE_SCHEME = "R17_TWO_PERSON_MAKER_CHECKER_V1"
LEGACY_GOVERNANCE_SCHEME = "FOUR_PERSON_SEPARATION_V1"


class SourceNotFound(LookupError):
    pass


class RepositoryConflict(RuntimeError):
    pass


def _governance_separation_actor_ids(
    *,
    scheme: str,
    maker_actor_ids: frozenset[UUID],
    prior_approver_actor_ids: frozenset[UUID],
) -> frozenset[UUID]:
    """Return actors forbidden from the next approval.

    The bounded R17 cohort permits one independent checker to perform separate
    approval actions.  It never permits a maker to approve.  Unknown schemes
    deliberately inherit the stricter legacy rule.
    """

    if scheme == ROUND17_TWO_PERSON_GOVERNANCE_SCHEME:
        return maker_actor_ids
    return maker_actor_ids | prior_approver_actor_ids


@dataclass(frozen=True, slots=True)
class SourceRow:
    id: UUID
    registry_code: str | None
    name: str
    base_url: str
    channel: str
    source_type: str
    authority_level: str
    priority: str
    collection_method: str
    poll_interval_minutes: int
    owner: str
    state: SourceState
    enabled: bool
    lifecycle_state: SourceLifecycleState
    trial_kind: SourceTrialKind | None
    registered_by: UUID | None
    governance_owner_id: UUID | None
    country_codes: tuple[str, ...]
    region_codes: tuple[str, ...]
    language_tags: tuple[str, ...]
    industries: tuple[str, ...]
    content_domains: tuple[str, ...]
    declared_roles: tuple[str, ...]
    current_policy_version_id: UUID | None
    current_connector_config_version_id: UUID | None
    current_trial_run_id: UUID | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyRow:
    id: UUID
    policy_version: str
    status: str
    document: dict[str, Any]
    document_sha256: str
    valid_until: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OnboardingRow:
    id: UUID
    source_policy_id: UUID
    record: dict[str, Any]
    record_sha256: str
    fixture_count: int
    fixture_set_sha256: str | None
    valid_until: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LifecycleFacts:
    policy_valid: bool
    policy_valid_until: datetime | None
    robots_allowed: bool
    terms_allowed: bool
    copyright_allowed: bool
    governance_owner_present: bool
    compliance_approved: bool
    connector_config_current: bool
    trial_kind: SourceTrialKind | None
    live_trial_succeeded: bool
    production_approval_current: bool
    separation_actor_ids: frozenset[UUID]
    current_trial_pending: bool = False


@dataclass(frozen=True, slots=True)
class FixtureReplayCapture:
    id: UUID
    raw_object_id: UUID
    object_key: str
    content_sha256: str
    byte_size: int
    declared_mime: str
    detected_mime: str
    requested_url: str
    final_url: str
    http_status: int
    etag: str | None
    last_modified: str | None
    filename: str
    title: str | None
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class FixtureReplayBundle:
    source_id: UUID
    trial_run_id: UUID
    connector_config_version_id: UUID
    connector_type: str
    config_document: dict[str, Any]
    allowed_hosts: tuple[str, ...]
    replay_status: str | None
    captures: tuple[FixtureReplayCapture, ...]


class SourceVaultRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_sources(self) -> list[SourceRow]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, registry_code, name, base_url, channel, source_type,
                               authority_level, priority, collection_method,
                               poll_interval_minutes, owner, state, enabled,
                               lifecycle_state, trial_kind, registered_by,
                               governance_owner_id, country_codes, region_codes,
                               language_tags, industries, content_domains, declared_roles,
                               current_policy_version_id, current_connector_config_version_id,
                               current_trial_run_id, created_at
                        FROM source
                        ORDER BY priority, registry_code NULLS LAST, created_at
                        """
                    )
                )
            ).mappings()
            return [_source_row(row) for row in rows]

    async def get_source(self, source_id: UUID) -> SourceRow:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, registry_code, name, base_url, channel, source_type,
                               authority_level, priority, collection_method,
                               poll_interval_minutes, owner, state, enabled,
                               lifecycle_state, trial_kind, registered_by,
                               governance_owner_id, country_codes, region_codes,
                               language_tags, industries, content_domains, declared_roles,
                               current_policy_version_id, current_connector_config_version_id,
                               current_trial_run_id, created_at
                        FROM source WHERE id = :source_id
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source does not exist")
        return _source_row(row)

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> SourceRow:
        source_id = uuid7()
        audit_id = uuid7()
        values = payload.model_dump(mode="python") | {
            "id": source_id,
            "actor_id": actor_id,
            "request_id": request_id,
            "audit_id": audit_id,
            "now": now,
        }
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT register_source_candidate(
                        :id, :name, :base_url, :channel, :source_type,
                        :authority_level, :priority, :collection_method,
                        :poll_interval_minutes, :owner, :governance_owner_id,
                        :country_codes, :region_codes, :language_tags,
                        :industries, :content_domains, :declared_roles,
                        :actor_id, :request_id, :audit_id, :now
                    )
                    """
                ),
                values,
            )
        return await self.get_source(source_id)

    async def lifecycle_facts(self, source_id: UUID, *, now: datetime) -> LifecycleFacts:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              p.valid_until,
                              COALESCE(
                                p.valid_from <= :now AND p.valid_until > :now, false
                              ) AS policy_valid,
                              COALESCE(p.document #>> '{robots_review,result}' = 'ALLOWED', false)
                                AS robots_allowed,
                              COALESCE(p.document #>> '{terms_review,result}' = 'ALLOWED', false)
                                AS terms_allowed,
                              COALESCE(
                                p.document #>> '{copyright_review,result}' = 'ALLOWED', false
                              )
                                AS copyright_allowed,
                              s.governance_owner_id IS NOT NULL AS governance_owner_present,
                              COALESCE(source_v2_policy_compliance_approved(
                                s.id,s.current_policy_version_id,:now
                              ),false) AS compliance_approved,
                              COALESCE(c.validation_status = 'VALID', false)
                                AS connector_config_current,
                              r.kind AS trial_kind,
                              COALESCE(rr.status = 'SUCCEEDED' AND r.kind = 'LIVE_TRIAL', false)
                                AS live_trial_succeeded,
                              COALESCE(r.id IS NOT NULL AND rr.trial_run_id IS NULL, false)
                                AS current_trial_pending,
                              EXISTS (
                                SELECT 1 FROM source_governance_decision d
                                 WHERE d.source_id = s.id
                                   AND d.policy_version_id = s.current_policy_version_id
                                   AND d.connector_config_version_id =
                                       s.current_connector_config_version_id
                                   AND d.trial_run_id = s.current_trial_run_id
                                   AND d.decision_type = 'PRODUCTION_APPROVAL'
                                   AND d.outcome = 'APPROVED'
                                   AND (d.valid_until IS NULL OR d.valid_until > :now)
                              ) AS production_approval_current,
                              s.registered_by, p.submitted_by AS policy_submitter,
                              c.created_by AS config_submitter,
                              r.requested_by AS trial_requester,
                              COALESCE(
                                assignment.scheme, :legacy_governance_scheme
                              ) AS governance_scheme,
                              (
                                SELECT d.decided_by
                                  FROM source_governance_decision d
                                 WHERE d.source_id=s.id
                                   AND d.policy_version_id=s.current_policy_version_id
                                   AND d.decision_type='COMPLIANCE'
                                 ORDER BY d.created_at DESC,d.id DESC LIMIT 1
                              ) AS compliance_approver,
                              (
                                SELECT d.decided_by
                                  FROM source_governance_decision d
                                 WHERE d.id=r.authorization_decision_id
                                   AND d.source_id=s.id
                                   AND d.decision_type='LIVE_TRIAL_AUTHORIZATION'
                              ) AS trial_authorizer,
                              ARRAY(
                                SELECT DISTINCT audit.actor_id
                                  FROM fetch_schedule schedule
                                  JOIN audit_log audit
                                    ON audit.target_type='fetch_schedule'
                                   AND audit.target_id=schedule.id
                                   AND audit.event_type='FETCH_SCHEDULE_UPDATED'
                                 WHERE schedule.source_id=s.id
                              ) AS schedule_maker_ids
                            FROM source s
                            LEFT JOIN source_governance_scheme_assignment assignment
                              ON assignment.source_id=s.id
                            LEFT JOIN source_policy_version p
                              ON p.id = s.current_policy_version_id AND p.source_id = s.id
                            LEFT JOIN connector_config_version c
                              ON c.id = s.current_connector_config_version_id
                             AND c.source_id = s.id AND c.policy_version_id=p.id
                            LEFT JOIN source_trial_run r
                              ON r.id = s.current_trial_run_id AND r.source_id = s.id
                             AND r.policy_version_id=p.id
                             AND r.connector_config_version_id=c.id
                            LEFT JOIN source_trial_run_result rr ON rr.trial_run_id = r.id
                            WHERE s.id = :source_id
                            """
                        ),
                        {
                            "source_id": source_id,
                            "now": now,
                            "legacy_governance_scheme": LEGACY_GOVERNANCE_SCHEME,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source does not exist")
        schedule_makers = row["schedule_maker_ids"]
        maker_actors = frozenset(
            value
            for value in (
                row["registered_by"],
                row["policy_submitter"],
                row["config_submitter"],
                row["trial_requester"],
                *(schedule_makers if isinstance(schedule_makers, list | tuple) else ()),
            )
            if isinstance(value, UUID)
        )
        prior_approvers = frozenset(
            value
            for value in (
                row["compliance_approver"],
                row["trial_authorizer"],
            )
            if isinstance(value, UUID)
        )
        actors = _governance_separation_actor_ids(
            scheme=str(row["governance_scheme"]),
            maker_actor_ids=maker_actors,
            prior_approver_actor_ids=prior_approvers,
        )
        return LifecycleFacts(
            policy_valid=bool(row["policy_valid"]),
            policy_valid_until=row["valid_until"],
            robots_allowed=bool(row["robots_allowed"]),
            terms_allowed=bool(row["terms_allowed"]),
            copyright_allowed=bool(row["copyright_allowed"]),
            governance_owner_present=bool(row["governance_owner_present"]),
            compliance_approved=bool(row["compliance_approved"]),
            connector_config_current=bool(row["connector_config_current"]),
            trial_kind=(None if row["trial_kind"] is None else SourceTrialKind(row["trial_kind"])),
            live_trial_succeeded=bool(row["live_trial_succeeded"]),
            production_approval_current=bool(row["production_approval_current"]),
            separation_actor_ids=actors,
            current_trial_pending=bool(row["current_trial_pending"]),
        )

    async def assign_round17_governance_scheme(
        self,
        source_id: UUID,
        *,
        cohort_key: str,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> None:
        assignment_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT assign_round17_two_person_governance(
                      :assignment_id,:source_id,:cohort_key,:actor_id,
                      :reason,:request_id,:audit_id,:now
                    )
                    """
                ),
                {
                    "assignment_id": assignment_id,
                    "source_id": source_id,
                    "cohort_key": cohort_key,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )

    async def round17_source_approver_binding_matches(
        self,
        *,
        actor_id: UUID,
        display_name: str,
        oidc_issuer_sha256: str,
        oidc_subject_sha256: str,
    ) -> bool:
        async with self._engine.connect() as connection:
            matched = (
                await connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                          SELECT 1
                            FROM round17_staff_binding
                           WHERE actor_id=:actor_id
                             AND display_name=:display_name
                             AND responsibility='SOURCE_APPROVER'
                             AND local_identity=false
                             AND oidc_issuer_sha256=:oidc_issuer_sha256
                             AND oidc_subject_sha256=:oidc_subject_sha256
                        )
                        """
                    ),
                    {
                        "actor_id": actor_id,
                        "display_name": display_name,
                        "oidc_issuer_sha256": oidc_issuer_sha256,
                        "oidc_subject_sha256": oidc_subject_sha256,
                    },
                )
            ).scalar_one()
        return bool(matched)

    async def submit_policy_version(
        self,
        source_id: UUID,
        payload: SourcePolicyV2Submission,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        policy_id, audit_id = uuid7(), uuid7()
        document = payload.model_dump(mode="json")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT submit_source_policy_version(
                      :source_id, :policy_id, :schema_version, :policy_version,
                      CAST(:document AS jsonb), :valid_from, :valid_until,
                      :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "schema_version": payload.schema_version,
                    "policy_version": payload.policy_version,
                    "document": _json(document),
                    "valid_from": payload.valid_from.astimezone(UTC),
                    "valid_until": payload.valid_until.astimezone(UTC),
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return policy_id

    async def decide_policy_version(
        self,
        source_id: UUID,
        policy_id: UUID,
        outcome: SourcePolicyDecisionOutcome,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        decision_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT decide_source_policy_version(
                      :source_id, :policy_id, :decision_id, :outcome, :actor_id,
                      :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "decision_id": decision_id,
                    "outcome": outcome.value,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return decision_id

    async def list_policy_versions(self, source_id: UUID) -> list[SourcePolicyVersionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT p.id, p.source_id, p.schema_version, p.policy_version,
                               CASE WHEN p.valid_until <= now() THEN 'EXPIRED'
                                    ELSE COALESCE(decision.outcome, 'PENDING_REVIEW') END status,
                               p.valid_from, p.valid_until, p.document_sha256, p.document,
                               p.submitted_by, decision.decided_by, p.created_at
                          FROM source_policy_version p
                          LEFT JOIN LATERAL (
                            SELECT d.outcome, d.decided_by
                              FROM source_governance_decision d
                             WHERE d.policy_version_id = p.id
                               AND d.decision_type = 'COMPLIANCE'
                             ORDER BY d.created_at DESC, d.id DESC LIMIT 1
                          ) decision ON true
                         WHERE p.source_id = :source_id
                         ORDER BY p.created_at DESC, p.id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [SourcePolicyVersionView.model_validate(dict(row)) for row in rows]

    async def current_policy_allowed_hosts(
        self, source_id: UUID, *, now: datetime
    ) -> tuple[str, ...]:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    """
                    SELECT p.document #> '{fetch,allowed_domains}'
                      FROM source s
                      JOIN source_policy_version p ON p.id=s.current_policy_version_id
                     WHERE s.id=:source_id AND p.source_id=s.id
                       AND p.valid_from <= :now AND p.valid_until > :now
                       AND source_v2_policy_compliance_approved(
                             s.id,p.id,:now
                           ) IS TRUE
                    """
                ),
                {"source_id": source_id, "now": now},
            )
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise RepositoryConflict("a current approved source policy is required")
        return tuple(value)

    async def list_connector_definitions(self) -> list[ConnectorDefinitionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, connector_type, definition_version, schema_version,
                               schema_document, schema_sha256, executor_key, capabilities
                          FROM connector_definition
                         ORDER BY connector_type, definition_version
                        """
                    )
                )
            ).mappings()
        return [ConnectorDefinitionView.model_validate(dict(row)) for row in rows]

    async def connector_definition(
        self, connector_type: ConnectorType, definition_version: str
    ) -> ConnectorDefinitionView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id, connector_type, definition_version, schema_version,
                                   schema_document, schema_sha256, executor_key, capabilities
                              FROM connector_definition
                             WHERE connector_type=:connector_type
                               AND definition_version=:definition_version
                            """
                        ),
                        {
                            "connector_type": connector_type.value,
                            "definition_version": definition_version,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise RepositoryConflict("connector definition does not exist")
        return ConnectorDefinitionView.model_validate(dict(row))

    async def save_connector_config(
        self,
        source_id: UUID,
        *,
        definition_id: UUID,
        config_document: dict[str, object],
        credential_ref: str | None,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> UUID:
        config_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            version_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COALESCE(max(version_number),0)+1 next_version,
                                   (array_agg(id ORDER BY version_number DESC))[1] latest_id
                              FROM connector_config_version
                             WHERE source_id=:source_id
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    SELECT save_source_connector_config(
                      :source_id, :config_id, :definition_id, :version_number,
                      CAST(:config_document AS jsonb), :credential_ref,
                      :supersedes_id, :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "config_id": config_id,
                    "definition_id": definition_id,
                    "version_number": version_row["next_version"],
                    "config_document": _json(config_document),
                    "credential_ref": credential_ref,
                    "supersedes_id": version_row["latest_id"],
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return config_id

    async def list_connector_configs(self, source_id: UUID) -> list[ConnectorConfigVersionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT c.id, c.source_id, c.policy_version_id, d.connector_type,
                               d.definition_version, c.version_number, c.config_sha256,
                               c.config_document AS config, c.allowed_hosts,
                               c.credential_ref IS NOT NULL
                                 AS credential_configured,
                               c.validation_status, c.created_by, c.created_at
                          FROM connector_config_version c
                          JOIN connector_definition d ON d.id=c.connector_definition_id
                         WHERE c.source_id=:source_id
                         ORDER BY c.version_number DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [ConnectorConfigVersionView.model_validate(dict(row)) for row in rows]

    async def update_governance_metadata(
        self,
        source_id: UUID,
        payload: SourceGovernanceMetadataUpdate,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT update_source_governance_metadata(
                      :source_id, :governance_owner_id, :country_codes,
                      :region_codes, :language_tags, :industries, :content_domains,
                      :declared_roles, :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "governance_owner_id": payload.governance_owner_id,
                    "country_codes": payload.country_codes,
                    "region_codes": payload.region_codes,
                    "language_tags": payload.language_tags,
                    "industries": [value.value for value in payload.industries],
                    "content_domains": [value.value for value in payload.content_domains],
                    "declared_roles": [value.value for value in payload.declared_roles],
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )

    async def append_assessments(
        self,
        source_id: UUID,
        payload: SourceAssessmentSubmission,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        authority, independence = payload.authority, payload.independence
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT append_source_assessments(
                      :source_id, :authority_id, :authority_level,
                      :authority_rule_version, :authority_reason_codes,
                      :authority_evidence_refs, :authority_assessed_at,
                      :independence_id, :independence_level,
                      :independence_rule_version, :independence_reason_codes,
                      :independence_evidence_refs, :independence_assessed_at,
                      :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "authority_id": uuid7(),
                    "authority_level": authority.level.value,
                    "authority_rule_version": authority.rule_version,
                    "authority_reason_codes": authority.reason_codes,
                    "authority_evidence_refs": authority.evidence_refs,
                    "authority_assessed_at": authority.assessed_at,
                    "independence_id": uuid7(),
                    "independence_level": independence.level.value,
                    "independence_rule_version": independence.rule_version,
                    "independence_reason_codes": independence.reason_codes,
                    "independence_evidence_refs": independence.evidence_refs,
                    "independence_assessed_at": independence.assessed_at,
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )

    async def latest_assessments(
        self, source_id: UUID
    ) -> tuple[SourceAuthorityAssessment | None, SourceIndependenceAssessment | None]:
        async with self._engine.connect() as connection:
            authority = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT authority_level AS level, rule_version, reason_codes,
                                   evidence_refs, assessed_at
                              FROM source_authority_assessment
                             WHERE source_id=:source_id
                             ORDER BY assessed_at DESC, id DESC LIMIT 1
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            independence = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT independence_level AS level, rule_version, reason_codes,
                                   evidence_refs, assessed_at
                              FROM source_independence_assessment
                             WHERE source_id=:source_id
                             ORDER BY assessed_at DESC, id DESC LIMIT 1
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return (
            None
            if authority is None
            else SourceAuthorityAssessment.model_validate(dict(authority)),
            None
            if independence is None
            else SourceIndependenceAssessment.model_validate(dict(independence)),
        )

    async def start_trial_run(
        self,
        source_id: UUID,
        payload: SourceTrialRunRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        trial_id, decision_id, event_id, audit_id = (
            uuid7(),
            uuid7(),
            uuid7(),
            uuid7(),
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT start_source_trial_run(
                      :source_id, :trial_id, :kind, :policy_id, :config_id,
                      :decision_id, :actor_id, :reason, :request_id,
                      :event_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "trial_id": trial_id,
                    "kind": payload.kind.value,
                    "policy_id": payload.policy_version_id,
                    "config_id": payload.connector_config_version_id,
                    "decision_id": decision_id,
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return trial_id

    async def complete_trial_run(
        self,
        trial_id: UUID,
        status: SourceTrialRunStatus,
        quality_summary: SourceTrialQualitySummary,
        *,
        raw_namespace: str,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> tuple[UUID, SourceTrialKind]:
        if status not in {
            SourceTrialRunStatus.SUCCEEDED,
            SourceTrialRunStatus.FAILED,
            SourceTrialRunStatus.CANCELLED,
        }:
            raise RepositoryConflict("source trial completion status is not terminal")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT source_id,kind FROM source_trial_run WHERE id=:trial_id"),
                        {"trial_id": trial_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SourceNotFound("source trial does not exist")
            await connection.execute(
                text(
                    """
                    SELECT complete_source_trial_run_with_audit(
                      :trial_id,:status,CAST(:quality_summary AS jsonb),
                      :raw_namespace,:actor_id,:reason,:request_id,:audit_id,:now
                    )
                    """
                ),
                {
                    "trial_id": trial_id,
                    "status": status.value,
                    "quality_summary": _json(quality_summary.model_dump(mode="json")),
                    "raw_namespace": raw_namespace,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )
        return row["source_id"], SourceTrialKind(row["kind"])

    async def fixture_trial_quality(
        self, source_id: UUID, trial_id: UUID
    ) -> SourceTrialQualitySummary:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source_trial_quality_summary(r.id) AS quality_summary
                              FROM source_trial_run r
                              JOIN source s ON s.id=r.source_id
                              LEFT JOIN source_trial_run_result result
                                ON result.trial_run_id=r.id
                             WHERE r.id=:trial_id AND r.source_id=:source_id
                               AND r.kind='FIXTURE_REPLAY'
                               AND r.execution_domain='FIXTURE'
                               AND s.lifecycle_state='TRIAL'
                               AND s.current_trial_run_id=r.id
                               AND result.trial_run_id IS NULL
                            """
                        ),
                        {"trial_id": trial_id, "source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise RepositoryConflict("fixture trial is not the current pending replay")
        return SourceTrialQualitySummary.model_validate(row["quality_summary"])

    async def fixture_replay_bundle(
        self, source_id: UUID, trial_id: UUID
    ) -> FixtureReplayBundle:
        async with self._engine.connect() as connection:
            header = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id AS trial_run_id, r.source_id,
                                   r.connector_config_version_id,
                                   definition.connector_type,
                                   config.config_document, config.allowed_hosts,
                                   replay.status AS replay_status
                              FROM source_trial_run r
                              JOIN source s
                                ON s.id=r.source_id
                               AND s.lifecycle_state='TRIAL'
                               AND s.trial_kind='FIXTURE_REPLAY'
                               AND s.current_trial_run_id=r.id
                              JOIN connector_config_version config
                                ON config.id=r.connector_config_version_id
                               AND config.source_id=r.source_id
                               AND config.validation_status='VALID'
                              JOIN connector_definition definition
                                ON definition.id=config.connector_definition_id
                              LEFT JOIN source_fixture_replay_result replay
                                ON replay.trial_run_id=r.id
                             WHERE r.id=:trial_id AND r.source_id=:source_id
                               AND r.kind='FIXTURE_REPLAY'
                               AND r.execution_domain='FIXTURE'
                               AND NOT EXISTS (
                                 SELECT 1 FROM source_trial_run_result result
                                  WHERE result.trial_run_id=r.id
                               )
                            """
                        ),
                        {"trial_id": trial_id, "source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            if header is None:
                raise RepositoryConflict("fixture trial is not the current pending replay")
            capture_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT capture.id, capture.raw_object_id, raw.object_key,
                               raw.sha256 AS content_sha256, raw.byte_size,
                               raw.declared_mime, raw.detected_mime,
                               capture.requested_url, capture.final_url,
                               capture.http_status, capture.etag,
                               capture.last_modified, capture.captured_at,
                               COALESCE(version.original_filename, 'fixture.bin') filename,
                               version.title
                          FROM raw_object_capture capture
                          JOIN raw_object raw ON raw.id=capture.raw_object_id
                          LEFT JOIN LATERAL (
                            SELECT candidate.original_filename,candidate.title
                              FROM document_version candidate
                              JOIN document linked_document
                                ON linked_document.id=candidate.document_id
                               AND linked_document.source_id=capture.source_id
                             WHERE candidate.raw_object_id=capture.raw_object_id
                               AND candidate.execution_domain='FIXTURE'
                             ORDER BY candidate.acquired_at DESC,candidate.id DESC
                             LIMIT 1
                          ) version ON true
                         WHERE capture.trial_run_id=:trial_id
                           AND capture.source_id=:source_id
                           AND capture.execution_domain='FIXTURE'
                           AND capture.arrived_after_close=false
                         ORDER BY capture.captured_at,capture.id
                        """
                    ),
                    {"trial_id": trial_id, "source_id": source_id},
                )
            ).mappings().all()
        config_document = header["config_document"]
        allowed_hosts = header["allowed_hosts"]
        if not isinstance(config_document, dict) or not isinstance(allowed_hosts, list):
            raise RepositoryConflict("fixture connector configuration is malformed")
        return FixtureReplayBundle(
            source_id=header["source_id"],
            trial_run_id=header["trial_run_id"],
            connector_config_version_id=header["connector_config_version_id"],
            connector_type=str(header["connector_type"]),
            config_document=dict(config_document),
            allowed_hosts=tuple(str(host) for host in allowed_hosts),
            replay_status=(
                None if header["replay_status"] is None else str(header["replay_status"])
            ),
            captures=tuple(
                FixtureReplayCapture(
                    id=row["id"],
                    raw_object_id=row["raw_object_id"],
                    object_key=str(row["object_key"]),
                    content_sha256=str(row["content_sha256"]),
                    byte_size=int(row["byte_size"]),
                    declared_mime=str(row["declared_mime"]),
                    detected_mime=str(row["detected_mime"]),
                    requested_url=str(row["requested_url"]),
                    final_url=str(row["final_url"]),
                    http_status=int(row["http_status"]),
                    etag=None if row["etag"] is None else str(row["etag"]),
                    last_modified=(
                        None
                        if row["last_modified"] is None
                        else str(row["last_modified"])
                    ),
                    filename=str(row["filename"]),
                    title=None if row["title"] is None else str(row["title"]),
                    captured_at=row["captured_at"],
                )
                for row in capture_rows
            ),
        )

    async def record_fixture_replay_result(
        self,
        bundle: FixtureReplayBundle,
        *,
        status: str,
        reason_code: str,
        document_count: int,
        transport_call_count: int,
        actor_id: UUID,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT record_source_fixture_replay_result(
                      :trial_id,:source_id,:config_id,:status,
                      :reason_code,:raw_capture_count,:document_count,
                      :transport_call_count,:actor_id,:now
                    )
                    """
                ),
                {
                    "trial_id": bundle.trial_run_id,
                    "source_id": bundle.source_id,
                    "config_id": bundle.connector_config_version_id,
                    "status": status,
                    "reason_code": reason_code,
                    "raw_capture_count": len(bundle.captures),
                    "document_count": document_count,
                    "transport_call_count": transport_call_count,
                    "actor_id": actor_id,
                    "now": now,
                },
            )

    async def list_trial_runs(self, source_id: UUID) -> list[SourceTrialRunView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT r.id, r.source_id, r.kind,
                               COALESCE(result.status, 'PENDING') status,
                               r.policy_version_id, r.connector_config_version_id,
                               r.requested_by, r.created_at AS started_at,
                               result.completed_at, result.quality_summary, r.created_at
                          FROM source_trial_run r
                          LEFT JOIN source_trial_run_result result
                            ON result.trial_run_id = r.id
                         WHERE r.source_id = :source_id
                         ORDER BY r.created_at DESC, r.id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [
            SourceTrialRunView(
                id=row["id"],
                source_id=row["source_id"],
                kind=SourceTrialKind(row["kind"]),
                status=SourceTrialRunStatus(row["status"]),
                policy_version_id=row["policy_version_id"],
                connector_config_version_id=row["connector_config_version_id"],
                requested_by=row["requested_by"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                quality_summary=(
                    None
                    if row["quality_summary"] is None
                    else SourceTrialQualitySummary.model_validate(row["quality_summary"])
                ),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def approve_production(
        self,
        source_id: UUID,
        *,
        policy_version_id: UUID,
        connector_config_version_id: UUID,
        trial_run_id: UUID,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        decision_id, event_id, audit_id = uuid7(), uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT approve_source_production(
                      :source_id, :policy_id, :config_id, :trial_id, :decision_id,
                      :actor_id, :reason, :request_id, :event_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_version_id,
                    "config_id": connector_config_version_id,
                    "trial_id": trial_run_id,
                    "decision_id": decision_id,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return decision_id

    async def apply_lifecycle_action(
        self,
        source_id: UUID,
        action: str,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        event_id = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT apply_source_lifecycle_command(
                      :source_id, :action, :actor_id, :reason, :request_id,
                      :event_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "action": action,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "now": now,
                },
            )

    async def list_lifecycle_events(self, source_id: UUID) -> list[SourceLifecycleEventView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, source_id, from_state, to_state, action, reason_code,
                               reason, actor_id, policy_version_id,
                               governance_decision_id, migration_rule_version, created_at
                          FROM source_lifecycle_event
                         WHERE source_id = :source_id
                         ORDER BY created_at DESC, id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [SourceLifecycleEventView.model_validate(dict(row)) for row in rows]

    async def list_audit_events(self, source_id: UUID) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, event_type, actor_id, reason, request_id, created_at
                          FROM audit_log
                         WHERE (target_type = 'SOURCE' AND target_id = :source_id)
                            OR target_id IN (
                              SELECT id FROM source_policy_version
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM connector_config_version
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM source_trial_run
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM source_trial_rejected_raw_attempt
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM document
                               WHERE source_id = :source_id
                            )
                         ORDER BY created_at DESC, id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [dict(row) for row in rows]

    async def source_coverage(self, *, now: datetime) -> SourceCoverageMatrix:
        industries = [item.value for item in SourceIndustry]
        domains = [item.value for item in SourceContentDomain]
        source_types = [item.value for item in SourceType]
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH normalized AS (
                          SELECT s.id, s.lifecycle_state, s.source_type,
                                 industry, content_domain, region, language,
                                 (
                                   s.lifecycle_state = 'ACTIVE'
                                   AND p.valid_from <= :now AND p.valid_until > :now
                                   AND c.validation_status = 'VALID'
                                   AND r.kind = 'LIVE_TRIAL' AND result.status = 'SUCCEEDED'
                                   AND source_v2_policy_compliance_approved(
                                         s.id,p.id,:now
                                       ) IS TRUE
                                   AND EXISTS (
                                     SELECT 1 FROM source_governance_decision d
                                      WHERE d.source_id = s.id
                                        AND d.policy_version_id = p.id
                                        AND d.connector_config_version_id = c.id
                                        AND d.trial_run_id = r.id
                                        AND d.decision_type = 'PRODUCTION_APPROVAL'
                                        AND d.outcome = 'APPROVED'
                                        AND (d.valid_until IS NULL OR d.valid_until > :now)
                                   )
                                 ) effective_active
                            FROM source s
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.industries)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.industries END
                            ) industry
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.content_domains)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.content_domains END
                            ) content_domain
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.region_codes)>0 THEN s.region_codes
                                   WHEN cardinality(s.country_codes)>0 THEN s.country_codes
                                   ELSE ARRAY['UNKNOWN']::text[] END
                            ) region
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.language_tags)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.language_tags END
                            ) language
                            LEFT JOIN source_policy_version p
                              ON p.id=s.current_policy_version_id AND p.source_id=s.id
                            LEFT JOIN connector_config_version c
                              ON c.id=s.current_connector_config_version_id
                             AND c.source_id=s.id AND c.policy_version_id=p.id
                            LEFT JOIN source_trial_run r
                              ON r.id=s.current_trial_run_id AND r.source_id=s.id
                             AND r.policy_version_id=p.id
                             AND r.connector_config_version_id=c.id
                            LEFT JOIN source_trial_run_result result ON result.trial_run_id=r.id
                        ), observed_geo AS (
                          SELECT DISTINCT region, language FROM normalized
                          UNION SELECT 'UNKNOWN','UNKNOWN'
                        ), grid AS (
                          SELECT industry, content_domain, source_type, region, language
                            FROM unnest(CAST(:industries AS text[])) industry
                            CROSS JOIN unnest(CAST(:domains AS text[])) content_domain
                            CROSS JOIN unnest(CAST(:source_types AS text[])) source_type
                            CROSS JOIN observed_geo
                        )
                        SELECT grid.industry, grid.content_domain, grid.source_type,
                               grid.region, grid.language,
                               count(normalized.id) FILTER (
                                 WHERE normalized.lifecycle_state IN
                                   ('CANDIDATE','COMPLIANCE_REVIEW')
                               ) candidate_count,
                               count(normalized.id) FILTER (
                                 WHERE normalized.lifecycle_state='TRIAL'
                               ) trial_count,
                               count(normalized.id) FILTER (
                                 WHERE normalized.effective_active
                               ) active_count
                          FROM grid
                          LEFT JOIN normalized USING (
                            industry,content_domain,source_type,region,language
                          )
                         GROUP BY grid.industry, grid.content_domain, grid.source_type,
                                  grid.region, grid.language
                         ORDER BY grid.industry, grid.content_domain, grid.source_type,
                                  grid.region, grid.language
                        """
                    ),
                    {
                        "now": now,
                        "industries": industries,
                        "domains": domains,
                        "source_types": source_types,
                    },
                )
            ).mappings()
        cells = [
            SourceCoverageCell(
                industry=SourceIndustry(row["industry"]),
                content_domain=SourceContentDomain(row["content_domain"]),
                source_type=SourceType(row["source_type"]),
                region=row["region"],
                language=row["language"],
                candidate_count=row["candidate_count"],
                trial_count=row["trial_count"],
                active_count=row["active_count"],
                gap=row["active_count"] == 0,
            )
            for row in rows
        ]
        return SourceCoverageMatrix(
            generated_at=now,
            cells=cells,
            gap_cell_count=sum(cell.gap for cell in cells),
        )

    async def latest_policy(self, source_id: UUID) -> PolicyRow | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, policy_version, status, document, document_sha256,
                               valid_until, created_at
                        FROM source_policy
                        WHERE source_id = :source_id
                        ORDER BY created_at DESC, id DESC LIMIT 1
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _policy_row(row)

    async def latest_onboarding(self, source_id: UUID) -> OnboardingRow | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, source_policy_id, record, record_sha256, fixture_count,
                               fixture_set_sha256, valid_until, created_at
                        FROM source_onboarding_record
                        WHERE source_id = :source_id
                        ORDER BY created_at DESC, id DESC LIMIT 1
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _onboarding_row(row)

    async def fixture_hashes(self, source_id: UUID) -> list[str]:
        async with self._engine.connect() as connection:
            values = await connection.scalars(
                text(
                    """
                    SELECT DISTINCT document_version.content_hash
                    FROM document_version
                    JOIN document ON document.id = document_version.document_id
                    WHERE document.source_id = :source_id
                      AND document.admission_fixture = true
                    ORDER BY document_version.content_hash
                    """
                ),
                {"source_id": source_id},
            )
            return list(values)

    async def save_policy(
        self,
        source_id: UUID,
        *,
        policy_version: str,
        status: str,
        document: dict[str, Any],
        document_sha256: str,
        valid_until: datetime,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        policy_id = uuid7()
        async with self._engine.begin() as connection:
            source = await self._locked_source(connection, source_id)
            await connection.execute(
                text(
                    """
                    INSERT INTO source_policy (
                        id, source_id, policy_version, status, document,
                        document_sha256, valid_until, created_by, created_at
                    ) VALUES (
                        :id, :source_id, :policy_version, :status,
                        CAST(:document AS jsonb), :document_sha256, :valid_until,
                        :actor_id, :now
                    )
                    """
                ),
                {
                    "id": policy_id,
                    "source_id": source_id,
                    "policy_version": policy_version,
                    "status": status,
                    "document": _json(document),
                    "document_sha256": document_sha256,
                    "valid_until": valid_until,
                    "actor_id": actor_id,
                    "now": now,
                },
            )
            if bool(source["enabled"]):
                await connection.execute(
                    text("UPDATE source SET enabled = false, updated_at = :now WHERE id = :id"),
                    {"id": source_id, "now": now},
                )
            await self._append_audit(
                connection,
                event_type="SOURCE_POLICY_CHANGED",
                actor_id=actor_id,
                target_type="source_policy",
                target_id=policy_id,
                before_state=None,
                after_state={
                    "source_id": str(source_id),
                    "policy_version": policy_version,
                    "status": status,
                    "document_sha256": document_sha256,
                    "source_disabled": bool(source["enabled"]),
                },
                reason="Source admission policy recorded",
                request_id=request_id,
                now=now,
            )

    async def save_onboarding(
        self,
        source_id: UUID,
        policy_id: UUID,
        *,
        record: dict[str, Any],
        record_sha256: str,
        fixture_count: int,
        fixture_set_sha256: str,
        valid_until: datetime,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        onboarding_id = uuid7()
        async with self._engine.begin() as connection:
            await self._locked_source(connection, source_id)
            await connection.execute(
                text(
                    """
                    INSERT INTO source_onboarding_record (
                        id, source_id, source_policy_id, record, record_sha256,
                        fixture_count, fixture_set_sha256, valid_until, created_by, created_at
                    ) VALUES (
                        :id, :source_id, :policy_id, CAST(:record AS jsonb),
                        :record_sha256, :fixture_count, :fixture_set_sha256,
                        :valid_until, :actor_id, :now
                    )
                    """
                ),
                {
                    "id": onboarding_id,
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "record": _json(record),
                    "record_sha256": record_sha256,
                    "fixture_count": fixture_count,
                    "fixture_set_sha256": fixture_set_sha256,
                    "valid_until": valid_until,
                    "actor_id": actor_id,
                    "now": now,
                },
            )
            await self._append_audit(
                connection,
                event_type="SOURCE_ONBOARDING_RECORDED",
                actor_id=actor_id,
                target_type="source_onboarding_record",
                target_id=onboarding_id,
                before_state=None,
                after_state={
                    "source_id": str(source_id),
                    "record_sha256": record_sha256,
                    "fixture_set_sha256": fixture_set_sha256,
                },
                reason="Source onboarding evidence recorded",
                request_id=request_id,
                now=now,
            )

    async def change_source(
        self,
        source_id: UUID,
        *,
        state: SourceState,
        enabled: bool,
        event_type: str,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            current = await self._locked_source(connection, source_id)
            before = {"state": str(current["state"]), "enabled": bool(current["enabled"])}
            after = {"state": state.value, "enabled": enabled}
            await connection.execute(
                text(
                    """
                    UPDATE source SET state = :state, enabled = :enabled, updated_at = :now
                    WHERE id = :source_id
                    """
                ),
                {"state": state.value, "enabled": enabled, "now": now, "source_id": source_id},
            )
            await self._append_audit(
                connection,
                event_type=event_type,
                actor_id=actor_id,
                target_type="source",
                target_id=source_id,
                before_state=before,
                after_state=after,
                reason=reason,
                request_id=request_id,
                now=now,
            )

    async def source_accepts_fixture(self, source_id: UUID, canonical_url: str) -> UUID | None:
        now = datetime.now(UTC)
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id AS trial_run_id,
                                   p.document #> '{fetch,allowed_domains}' allowed_domains,
                                   c.allowed_hosts
                              FROM source s
                              JOIN source_policy_version p
                                ON p.id=s.current_policy_version_id AND p.source_id=s.id
                              JOIN connector_config_version c
                                ON c.id=s.current_connector_config_version_id
                               AND c.source_id=s.id AND c.policy_version_id=p.id
                              JOIN source_trial_run r
                                ON r.id=s.current_trial_run_id AND r.source_id=s.id
                               AND r.policy_version_id=p.id
                               AND r.connector_config_version_id=c.id
                             WHERE s.id=:source_id AND s.lifecycle_state='TRIAL'
                               AND s.trial_kind='FIXTURE_REPLAY'
                               AND r.kind='FIXTURE_REPLAY' AND r.execution_domain='FIXTURE'
                               AND NOT EXISTS (
                                 SELECT 1 FROM source_trial_run_result result
                                  WHERE result.trial_run_id=r.id
                               )
                               AND c.validation_status='VALID'
                               AND p.valid_from <= :now AND p.valid_until > :now
                               AND source_v2_policy_compliance_approved(
                                     s.id,p.id,:now
                                   ) IS TRUE
                            """
                        ),
                        {"source_id": source_id, "now": now},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        hostname = urlsplit(canonical_url).hostname
        domains = row["allowed_domains"]
        allowed_hosts = row["allowed_hosts"]
        if hostname is None or not isinstance(domains, list) or not isinstance(allowed_hosts, list):
            return None
        normalized_host = hostname.rstrip(".").lower()
        return (
            row["trial_run_id"]
            if normalized_host in set(domains) and normalized_host in set(allowed_hosts)
            else None
        )

    async def raw_object_exists(self, content_hash: str) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM raw_object WHERE sha256 = :sha256)"),
                {"sha256": content_hash},
            )
        return bool(value)

    async def raw_object_security_blocked(self, content_hash: str) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1
                        FROM raw_object raw
                       WHERE raw.sha256=:sha256
                         AND (
                           raw.scan_status='REJECTED'
                           OR EXISTS (
                             SELECT 1 FROM raw_object_security_fact security
                              WHERE security.raw_object_id=raw.id
                                AND security.status IN ('REJECTED','QUARANTINED')
                           )
                         )
                    )
                    """
                ),
                {"sha256": content_hash},
            )
        return bool(value)

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse:
        version_created = False
        async with self._engine.begin() as connection:
            await self._locked_source(connection, record.source_id)
            if record.trial_run_id is None:
                raise RepositoryConflict("fixture upload has no trial authorization")
            raw_id = uuid7()
            inserted_raw = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
                            :detected_mime, 'CLEAN', :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": raw_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "declared_mime": record.declared_mime,
                        "detected_mime": record.detected_mime,
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            raw_deduplicated = inserted_raw is None
            if raw_deduplicated:
                raw_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
                if not isinstance(raw_id, UUID):
                    raise RepositoryConflict("raw object deduplication failed")
            await connection.execute(
                text(
                    """
                    INSERT INTO raw_object_security_fact (
                        id, raw_object_id, status, detected_mime,
                        rule_version, reason_code, created_at
                    ) VALUES (
                        :id, :raw_id, 'CLEAN', :detected_mime,
                        'source-vault-2.0.0', NULL, :created_at
                    )
                    ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                    """
                ),
                {
                    "id": uuid7(),
                    "raw_id": raw_id,
                    "detected_mime": record.detected_mime,
                    "created_at": record.acquired_at,
                },
            )
            capture_id = uuid7()
            await connection.execute(
                text(
                    """
                    SELECT append_source_trial_raw_capture(
                      :id,:raw_object_id,:source_id,:trial_run_id,'FIXTURE',
                      :url,:url,CAST('[]' AS jsonb),200,NULL,NULL,
                      :response_sha256,:captured_at
                    )
                    """
                ),
                {
                    "id": capture_id,
                    "raw_object_id": raw_id,
                    "source_id": record.source_id,
                    "trial_run_id": record.trial_run_id,
                    "url": record.canonical_url,
                    "response_sha256": record.response_sha256,
                    "captured_at": record.acquired_at,
                },
            )
            arrived_after_close = bool(
                await connection.scalar(
                    text("SELECT arrived_after_close FROM raw_object_capture WHERE id=:id"),
                    {"id": capture_id},
                )
            )

            document_id = uuid7()
            inserted_document = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO document (
                            id, source_id, canonical_url, document_kind,
                            first_discovered_at, current_version_id, admission_fixture
                        ) VALUES (
                            :id, :source_id, :url, :kind, :acquired_at, NULL,
                            :admission_fixture
                        )
                        ON CONFLICT (source_id, canonical_url) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": document_id,
                        "source_id": record.source_id,
                        "url": record.canonical_url,
                        "kind": record.document_kind,
                        "acquired_at": record.acquired_at,
                        "admission_fixture": record.admission_fixture,
                    },
                )
            ).scalar_one_or_none()
            if inserted_document is None:
                document_id = await connection.scalar(
                    text(
                        """
                        SELECT id FROM document
                        WHERE source_id = :source_id AND canonical_url = :url
                        FOR UPDATE
                        """
                    ),
                    {"source_id": record.source_id, "url": record.canonical_url},
                )
                if not isinstance(document_id, UUID):
                    raise RepositoryConflict("document upsert failed")

            existing_version = await connection.scalar(
                text(
                    """
                    SELECT id FROM document_version
                    WHERE document_id = :document_id AND content_hash = :content_hash
                    """
                ),
                {"document_id": document_id, "content_hash": record.content_hash},
            )
            if existing_version is None:
                next_number = int(
                    await connection.scalar(
                        text(
                            """
                            SELECT COALESCE(MAX(version_number), 0) + 1
                            FROM document_version WHERE document_id = :document_id
                            """
                        ),
                        {"document_id": document_id},
                    )
                )
                version_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version (
                            id, document_id, raw_object_id, version_number, content_hash,
                            original_filename, title, acquired_at, execution_domain,
                            raw_object_capture_id
                        ) VALUES (
                            :id, :document_id, :raw_object_id, :version_number,
                            :content_hash, :filename, :title, :acquired_at, 'FIXTURE',
                            :raw_object_capture_id
                        )
                        """
                    ),
                    {
                        "id": version_id,
                        "document_id": document_id,
                        "raw_object_id": raw_id,
                        "version_number": next_number,
                        "content_hash": record.content_hash,
                        "filename": record.filename,
                        "title": record.title,
                        "acquired_at": record.acquired_at,
                        "raw_object_capture_id": capture_id,
                    },
                )
                # Manual fixtures complete bounded parsing before this transaction.
                # Pipeline acquisitions remain non-terminal until their dedicated
                # parser/attachment workflow appends READY or a failure state.
                states = ["RECEIVED", "SECURITY_PASSED"]
                if record.admission_fixture and not arrived_after_close:
                    states.append("READY")
                elif arrived_after_close:
                    states.append("FAILED")
                for state_index, state in enumerate(states):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO document_version_state_event (
                                id, document_version_id, state, reason_code,
                                actor_type, created_at
                            ) VALUES (
                                :id, :version_id, :state, :reason_code,
                                'SYSTEM', :created_at
                            )
                            """
                        ),
                        {
                            "id": uuid7(),
                            "version_id": version_id,
                            "state": state,
                            "reason_code": (
                                "TRIAL_CLOSED_DURING_UPLOAD"
                                if state == "FAILED" and arrived_after_close
                                else None
                            ),
                            "created_at": record.acquired_at + timedelta(microseconds=state_index),
                        },
                    )
                if record.admission_fixture and not arrived_after_close:
                    await connection.execute(
                        text("UPDATE document SET current_version_id = :version_id WHERE id = :id"),
                        {"version_id": version_id, "id": document_id},
                    )
                version_created = True
            else:
                if not isinstance(existing_version, UUID):
                    raise RepositoryConflict("document version lookup failed")
                version_id = existing_version
            await self._append_audit(
                connection,
                event_type=(
                    "SOURCE_FIXTURE_UPLOAD_TERMINATED"
                    if arrived_after_close
                    else "SOURCE_FIXTURE_UPLOADED"
                ),
                actor_id=record.actor_id,
                target_type="document",
                target_id=document_id,
                before_state=None,
                after_state={
                    "content_hash": record.content_hash,
                    "raw_object_deduplicated": raw_deduplicated,
                    "version_created": version_created,
                    "arrived_after_close": arrived_after_close,
                },
                reason=(
                    "Authorized fixture upload arrived after trial closure"
                    if arrived_after_close
                    else "Manual source fixture uploaded"
                ),
                request_id=record.request_id,
                now=record.acquired_at,
            )
        document = await self._get_document_version(document_id, version_id)
        return FixtureUploadResponse(
            document=document,
            raw_object_deduplicated=raw_deduplicated,
            version_created=version_created,
        )

    async def record_attachment(self, record: AttachmentRecord) -> UUID:
        async with self._engine.begin() as connection:
            raw_object_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
                            :detected_mime, :scan_status, :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": record.raw_object_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "declared_mime": record.declared_mime,
                        "detected_mime": record.detected_mime,
                        "scan_status": (
                            "REJECTED" if record.globally_quarantined else "CLEAN"
                        ),
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            if not isinstance(raw_object_id, UUID):
                raw_object_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
            if not isinstance(raw_object_id, UUID):
                raise RepositoryConflict("attachment raw object upsert failed")
            if record.security_status == "CLEAN":
                blocked = await connection.scalar(
                    text(
                        """
                        SELECT raw.scan_status <> 'CLEAN'
                               OR EXISTS (
                                 SELECT 1 FROM raw_object_security_fact security
                                  WHERE security.raw_object_id=raw.id
                                    AND security.status IN ('REJECTED','QUARANTINED')
                               )
                          FROM raw_object raw WHERE raw.id=:raw_object_id
                        """
                    ),
                    {"raw_object_id": raw_object_id},
                )
                if blocked is not False:
                    raise RepositoryConflict("attachment raw object has rejected security history")
            if record.security_status == "CLEAN" or record.globally_quarantined:
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact (
                            id, raw_object_id, status, detected_mime,
                            rule_version, reason_code, created_at
                        ) VALUES (
                            :id, :raw_object_id, :status, :detected_mime,
                            :rule_version, :reason_code, :created_at
                        )
                        ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid7(),
                        "raw_object_id": raw_object_id,
                        "status": record.security_status,
                        "rule_version": (
                            "attachment-security-3.0.0-clean"
                            if record.security_status == "CLEAN"
                            else "attachment-security-3.0.0-negative"
                        ),
                        "detected_mime": record.detected_mime,
                        "reason_code": record.reason_code,
                        "created_at": record.acquired_at,
                    },
                )
            existing_id = await connection.scalar(
                text(
                    """
                    SELECT id
                    FROM document_attachment
                    WHERE document_version_id = :document_version_id
                      AND parent_attachment_id IS NOT DISTINCT FROM :parent_attachment_id
                      AND normalized_path = :normalized_path
                      AND raw_object_id = :raw_object_id
                    LIMIT 1
                    """
                ),
                {
                    "document_version_id": record.document_version_id,
                    "parent_attachment_id": record.parent_attachment_id,
                    "normalized_path": record.normalized_path,
                    "raw_object_id": raw_object_id,
                },
            )
            if isinstance(existing_id, UUID):
                return existing_id
            await connection.execute(
                text(
                    """
                    INSERT INTO document_attachment (
                        id, document_version_id, raw_object_id, filename, role,
                        parent_attachment_id, normalized_path, depth, detected_mime,
                        byte_size, security_status, created_at
                    ) VALUES (
                        :id, :document_version_id, :raw_object_id, :filename, :role,
                        :parent_attachment_id, :normalized_path, :depth, :detected_mime,
                        :byte_size, :security_status, :created_at
                    )
                    """
                ),
                {
                    "id": record.attachment_id,
                    "document_version_id": record.document_version_id,
                    "raw_object_id": raw_object_id,
                    "filename": record.filename,
                    "role": record.role,
                    "parent_attachment_id": record.parent_attachment_id,
                    "normalized_path": record.normalized_path,
                    "depth": record.depth,
                    "detected_mime": record.detected_mime,
                    "byte_size": record.byte_size,
                    "security_status": record.security_status,
                    "created_at": record.acquired_at,
                },
            )
        return record.attachment_id

    async def record_attachment_attempt(self, record: AttachmentAttemptRecord) -> UUID:
        async with self._engine.begin() as connection:
            attempt_id = await connection.scalar(
                text(
                    """
                    SELECT append_document_attachment_attempt(
                      :attempt_id,:document_version_id,:content_sha256,
                      :object_key,:storage_etag,:byte_size,:declared_mime,
                      :detected_mime,:filename_sha256,:normalized_path_sha256,
                      :canonical_url_sha256,:outcome,:reason_code,:occurred_at
                    )
                    """
                ),
                {
                    "attempt_id": record.attempt_id,
                    "document_version_id": record.document_version_id,
                    "content_sha256": record.content_hash,
                    "object_key": record.object_key,
                    "storage_etag": record.storage_etag,
                    "byte_size": record.byte_size,
                    "declared_mime": record.declared_mime,
                    "detected_mime": record.detected_mime,
                    "filename_sha256": record.filename_sha256,
                    "normalized_path_sha256": record.normalized_path_sha256,
                    "canonical_url_sha256": record.canonical_url_sha256,
                    "outcome": record.outcome,
                    "reason_code": record.reason_code,
                    "occurred_at": record.acquired_at,
                },
            )
        if not isinstance(attempt_id, UUID):
            raise RepositoryConflict("attachment attempt evidence was not appended")
        return attempt_id

    async def record_rejected_raw(self, record: RejectedRawRecord) -> UUID | None:
        async with self._engine.begin() as connection:
            if record.trial_run_id is None:
                raise RepositoryConflict("rejected fixture attempt has no trial context")
            if not record.globally_quarantined:
                contextual_raw_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256=:sha256"),
                    {"sha256": record.content_hash},
                )
                raw_id = contextual_raw_id if isinstance(contextual_raw_id, UUID) else None
                await self._append_rejected_trial_attempt(connection, record, raw_id)
                return raw_id
            raw_object_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
                            :detected_mime, 'REJECTED', :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": record.raw_object_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "declared_mime": record.declared_mime,
                        "detected_mime": record.detected_mime,
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            if not isinstance(raw_object_id, UUID):
                raw_object_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
            if not isinstance(raw_object_id, UUID):
                raise RepositoryConflict("rejected raw object upsert failed")
            affected_version_ids = list(
                await connection.scalars(
                    text(
                        """
                        SELECT version.id FROM document_version version
                         WHERE version.raw_object_id=:raw_object_id
                           AND NOT EXISTS (
                             SELECT 1 FROM document_version_state_event terminal
                              WHERE terminal.document_version_id=version.id
                                AND terminal.state IN ('QUARANTINED','FAILED')
                           )
                        """
                    ),
                    {"raw_object_id": raw_object_id},
                )
            )
            for version_id in affected_version_ids:
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version_state_event(
                          id,document_version_id,state,reason_code,actor_type,created_at
                        ) VALUES (
                          :id,:version_id,'QUARANTINED',:reason_code,'SYSTEM',
                          GREATEST(
                            CAST(:created_at AS timestamptz),
                            COALESCE((
                              SELECT max(existing.created_at) + interval '1 microsecond'
                                FROM document_version_state_event existing
                               WHERE existing.document_version_id=:version_id
                            ),CAST(:created_at AS timestamptz))
                          )
                        )
                        """
                    ),
                    {
                        "id": uuid7(),
                        "version_id": version_id,
                        "reason_code": record.reason_code,
                        "created_at": record.acquired_at,
                    },
                )
            await connection.execute(
                text(
                    """
                    UPDATE document document_row
                       SET current_version_id=(
                         SELECT candidate.id
                           FROM document_version candidate
                           JOIN raw_object candidate_raw
                             ON candidate_raw.id=candidate.raw_object_id
                          WHERE candidate.document_id=document_row.id
                            AND candidate.raw_object_id<>:raw_object_id
                            AND candidate_raw.scan_status='CLEAN'
                            AND NOT EXISTS (
                              SELECT 1 FROM raw_object_security_fact negative
                               WHERE negative.raw_object_id=candidate_raw.id
                                 AND negative.status IN ('REJECTED','QUARANTINED')
                            )
                            AND (
                              SELECT state.state
                                FROM document_version_state_event state
                               WHERE state.document_version_id=candidate.id
                               ORDER BY state.created_at DESC,state.id DESC LIMIT 1
                            )='READY'
                          ORDER BY candidate.version_number DESC,candidate.id DESC
                          LIMIT 1
                       )
                     WHERE document_row.current_version_id IN (
                       SELECT blocked.id FROM document_version blocked
                        WHERE blocked.raw_object_id=:raw_object_id
                     )
                    """
                ),
                {"raw_object_id": raw_object_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO raw_object_security_fact (
                        id, raw_object_id, status, detected_mime,
                        rule_version, reason_code, created_at
                    ) VALUES (
                        :id, :raw_object_id, 'QUARANTINED', :detected_mime,
                        'source-vault-3.0.0', :reason_code, :created_at
                    )
                    ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                    """
                ),
                {
                    "id": uuid7(),
                    "raw_object_id": raw_object_id,
                    "detected_mime": record.detected_mime,
                    "reason_code": record.reason_code,
                    "created_at": record.acquired_at,
                },
            )
            await self._append_rejected_trial_attempt(connection, record, raw_object_id)
        return raw_object_id

    async def _append_rejected_trial_attempt(
        self,
        connection: AsyncConnection,
        record: RejectedRawRecord,
        raw_object_id: UUID | None,
    ) -> None:
        if record.trial_run_id is None:
            raise RepositoryConflict("rejected fixture attempt has no trial context")
        attempt_id = uuid7()
        await connection.execute(
            text(
                """
                SELECT append_source_trial_rejected_raw_attempt(
                  :id,:source_id,:trial_run_id,:raw_object_id,:content_sha256,
                  :object_key,:canonical_url,:reason_code,:actor_id,:request_id,
                  :occurred_at
                )
                """
            ),
            {
                "id": attempt_id,
                "source_id": record.source_id,
                "trial_run_id": record.trial_run_id,
                "raw_object_id": raw_object_id,
                "content_sha256": record.content_hash,
                "object_key": record.object_key,
                "canonical_url": record.canonical_url,
                "reason_code": record.reason_code,
                "actor_id": record.actor_id,
                "request_id": record.request_id,
                "occurred_at": record.acquired_at,
            },
        )

    async def get_document(self, document_id: UUID) -> DocumentDetail:
        return await self._get_document_version(document_id, None)

    async def _get_document_version(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> DocumentDetail:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT d.id, d.source_id, s.name AS source_name, d.canonical_url,
                               d.document_kind, d.first_discovered_at,
                               v.id AS version_id, v.version_number, v.content_hash,
                               v.original_filename, v.title, v.acquired_at,
                               r.id AS raw_id, r.sha256, r.detected_mime,
                               r.byte_size, r.scan_status
                        FROM document d
                        JOIN source s ON s.id = d.source_id
                        JOIN document_version v
                          ON v.id = COALESCE(CAST(:version_id AS uuid), d.current_version_id)
                        JOIN raw_object r ON r.id = v.raw_object_id
                        WHERE d.id = :document_id
                        """
                        ),
                        {"document_id": document_id, "version_id": version_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("document does not exist")
        return DocumentDetail(
            id=row["id"],
            source_id=row["source_id"],
            source_name=row["source_name"],
            canonical_url=row["canonical_url"],
            document_kind=row["document_kind"],
            first_discovered_at=row["first_discovered_at"],
            current_version=DocumentVersionSummary(
                id=row["version_id"],
                version_number=row["version_number"],
                content_hash=row["content_hash"],
                original_filename=row["original_filename"],
                title=row["title"],
                acquired_at=row["acquired_at"],
            ),
            raw_object=RawObjectSummary(
                id=row["raw_id"],
                sha256=row["sha256"],
                detected_mime=row["detected_mime"],
                byte_size=row["byte_size"],
                scan_status=ScanStatus(row["scan_status"]),
            ),
        )

    async def _locked_source(self, connection: AsyncConnection, source_id: UUID) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT id,state,enabled,lifecycle_state,trial_kind,
                               current_trial_run_id
                          FROM source WHERE id=:id
                        """
                    ),
                    {"id": source_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise SourceNotFound("source does not exist")
        return row

    async def _append_audit(
        self,
        connection: AsyncConnection,
        *,
        event_type: str,
        actor_id: UUID,
        target_type: str,
        target_id: UUID,
        before_state: dict[str, Any] | None,
        after_state: dict[str, Any] | None,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> None:
        await connection.execute(
            text(
                """
                SELECT append_audit_event(
                    :id, :event_type, :actor_id, :target_type, :target_id,
                    CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                    :reason, :request_id, :created_at
                )
                """
            ),
            {
                "id": uuid7(),
                "event_type": event_type,
                "actor_id": actor_id,
                "target_type": target_type,
                "target_id": target_id,
                "before_state": None if before_state is None else _json(before_state),
                "after_state": None if after_state is None else _json(after_state),
                "reason": reason,
                "request_id": request_id,
                "created_at": now,
            },
        )


def _source_row(row: RowMapping) -> SourceRow:
    return SourceRow(
        id=row["id"],
        registry_code=row["registry_code"],
        name=row["name"],
        base_url=row["base_url"],
        channel=row["channel"],
        source_type=row["source_type"],
        authority_level=row["authority_level"],
        priority=row["priority"],
        collection_method=row["collection_method"],
        poll_interval_minutes=row["poll_interval_minutes"],
        owner=row["owner"],
        state=SourceState(row["state"]),
        enabled=row["enabled"],
        lifecycle_state=SourceLifecycleState(row["lifecycle_state"]),
        trial_kind=None if row["trial_kind"] is None else SourceTrialKind(row["trial_kind"]),
        registered_by=row["registered_by"],
        governance_owner_id=row["governance_owner_id"],
        country_codes=tuple(row["country_codes"]),
        region_codes=tuple(row["region_codes"]),
        language_tags=tuple(row["language_tags"]),
        industries=tuple(row["industries"]),
        content_domains=tuple(row["content_domains"]),
        declared_roles=tuple(row["declared_roles"]),
        current_policy_version_id=row["current_policy_version_id"],
        current_connector_config_version_id=row["current_connector_config_version_id"],
        current_trial_run_id=row["current_trial_run_id"],
        created_at=row["created_at"],
    )


def _policy_row(row: RowMapping) -> PolicyRow:
    return PolicyRow(
        id=row["id"],
        policy_version=row["policy_version"],
        status=row["status"],
        document=dict(row["document"]),
        document_sha256=row["document_sha256"],
        valid_until=row["valid_until"],
        created_at=row["created_at"],
    )


def _onboarding_row(row: RowMapping) -> OnboardingRow:
    return OnboardingRow(
        id=row["id"],
        source_policy_id=row["source_policy_id"],
        record=dict(row["record"]),
        record_sha256=row["record_sha256"],
        fixture_count=row["fixture_count"],
        fixture_set_sha256=row["fixture_set_sha256"],
        valid_until=row["valid_until"],
        created_at=row["created_at"],
    )


def canonical_json_hash(value: dict[str, Any]) -> str:
    return sha256(_json(value).encode()).hexdigest()


def fixture_set_hash(values: list[str]) -> str:
    return sha256("\n".join(sorted(set(values))).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
