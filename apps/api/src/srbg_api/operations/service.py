"""PostgreSQL-backed operational control plane."""

from __future__ import annotations

import json
from base64 import b64decode
from binascii import Error as BinasciiError
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    CircuitState,
    FetchScheduleStatus,
    FetchScheduleUpdate,
    FetchScheduleView,
    GoldAnnotationRequest,
    GoldAnnotationView,
    GoldArbitrationOption,
    GoldArbitrationPacket,
    GoldArbitrationRequest,
    GoldReleaseRequest,
    GoldReleaseView,
    GoldSampleKind,
    GoldTaskCreateRequest,
    GoldTaskView,
    MetricSample,
    OperationsOverview,
    OperatorTaskCompleteRequest,
    OperatorTaskCreateRequest,
    OperatorTaskStatus,
    OperatorTaskView,
    OperatorWorkCategory,
    OperatorWorkSessionCorrectionRequest,
    OperatorWorkSessionHeartbeatRequest,
    OperatorWorkSessionStopRequest,
    OperatorWorkSessionView,
    PilotMetrics,
    PilotSourceResumeRequest,
    PilotWindowCompleteRequest,
    PilotWindowCreateRequest,
    PilotWindowStartRequest,
    PilotWindowState,
    PilotWindowView,
    ReplayRequest,
    ReplayResult,
    ReplayTaskView,
    SourceAnomalyView,
    SourceHealthView,
)

from srbg_api.identifiers import uuid7
from srbg_api.operations.round17 import (
    PilotReadinessFacts,
    PilotSourceReadiness,
    evaluate_window_readiness,
)


class OperationsRejected(RuntimeError):
    pass


_GOLD_REQUIRED_COUNTS: dict[str, int] = {
    GoldSampleKind.DOCUMENT.value: 500,
    GoldSampleKind.PAIR.value: 300,
    GoldSampleKind.EVENT.value: 100,
    GoldSampleKind.CLAIM_EVIDENCE.value: 200,
    GoldSampleKind.SEARCH_QUESTION.value: 100,
}
_ROUND17_ROSTER_VERSION = "r17-sources-v0.1"
_ROUND17_METRIC_DEFINITION_VERSION = "phase2-round17-metrics-v1.0.0"
_ROUND17_GOLD_DEFINITION_VERSION = "phase2-round17-gold-v1.0.0"
_DIGITAL_SOURCE_CONTENT_DOMAINS = frozenset(
    {
        "DIGITAL_TRANSFORMATION_CASE",
        "RESEARCH_PAPER",
        "SOFTWARE_PLATFORM",
        "IOT_EQUIPMENT",
        "LOW_ALTITUDE_EQUIPMENT",
        "AI_APPLICATION",
    }
)
_SAFETY_SOURCE_CONTENT_DOMAINS = frozenset(
    {
        "SAFETY_REGULATION",
        "STANDARD_GUIDANCE",
        "ACCIDENT_INVESTIGATION",
        "OFFICIAL_NOTICE",
        "PENALTY",
        "RECTIFICATION",
    }
)


def _round17_leo_actor_is_attested(
    actor_id: UUID, attested_actor_id: UUID | None
) -> bool:
    return attested_actor_id is not None and actor_id == attested_actor_id


def _eventization_manifest_is_trusted(
    readiness: Mapping[str, Any] | RowMapping,
    *,
    source_code: str,
    leo_actor_id: UUID | None,
    trusted_public_key_base64: str | None,
    trusted_public_key_sha256: str | None,
) -> bool:
    """Verify a content-addressed, externally signed end-to-end readiness manifest."""

    if (
        leo_actor_id is None
        or str(readiness.get("verified_by")) != str(leo_actor_id)
        or trusted_public_key_base64 is None
        or trusted_public_key_sha256 is None
    ):
        return False
    manifest = readiness.get("verification_manifest")
    if not isinstance(manifest, dict):
        return False
    expected = {
        "schema_version": "round17-eventization-manifest-v1",
        "source_code": source_code,
        "source_id": str(readiness.get("source_id")),
        "policy_version_id": str(readiness.get("policy_version_id")),
        "connector_config_version_id": str(
            readiness.get("connector_config_version_id")
        ),
        "trial_run_id": str(readiness.get("trial_run_id")),
        "production_decision_id": str(readiness.get("production_decision_id")),
        "business_parser_profile": {
            "version": readiness.get("business_parser_profile_version"),
            "sha256": readiness.get("business_parser_profile_sha256"),
        },
        "claim_evidence_profile": {
            "version": readiness.get("claim_evidence_profile_version"),
            "sha256": readiness.get("claim_evidence_profile_sha256"),
        },
        "event_identity_profile": {
            "version": readiness.get("event_identity_profile_version"),
            "sha256": readiness.get("event_identity_profile_sha256"),
        },
        "publication_projection_profile": {
            "version": readiness.get("publication_projection_profile_version"),
            "sha256": readiness.get("publication_projection_profile_sha256"),
        },
        "verification_manifest_ref": readiness.get("verification_manifest_ref"),
        "outcome": "PASSED",
    }
    if manifest != expected:
        return False
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if sha256(canonical).hexdigest() != readiness.get("verification_manifest_sha256"):
        return False
    try:
        public_key_bytes = b64decode(trusted_public_key_base64, validate=True)
        signature = b64decode(str(readiness.get("verification_signature")), validate=True)
        if len(public_key_bytes) != 32 or len(signature) != 64:
            return False
        fingerprint = sha256(public_key_bytes).hexdigest()
        if (
            fingerprint != trusted_public_key_sha256
            or fingerprint != readiness.get("signer_public_key_sha256")
        ):
            return False
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, canonical)
    except (BinasciiError, InvalidSignature, TypeError, ValueError):
        return False
    return True


def _round17_snapshot_blockers(
    window: Mapping[str, Any] | RowMapping,
    *,
    observed_source_codes: Sequence[str],
    current_database_revision: str | None,
    baseline_commit_attestation: str | None,
    config_version_attestation: str | None,
    authoritative_source_codes: Sequence[str] | None,
) -> set[str]:
    """Compare a client-prepared snapshot with server and database authority facts."""

    blockers: set[str] = set()
    if baseline_commit_attestation is None:
        blockers.add("ROUND17_BASELINE_COMMIT_ATTESTATION_MISSING")
    elif window["baseline_commit"] != baseline_commit_attestation:
        blockers.add("ROUND17_BASELINE_COMMIT_ATTESTATION_MISMATCH")
    if config_version_attestation is None:
        blockers.add("ROUND17_CONFIG_VERSION_ATTESTATION_MISSING")
    elif window["config_version"] != config_version_attestation:
        blockers.add("ROUND17_CONFIG_VERSION_ATTESTATION_MISMATCH")
    if (
        authoritative_source_codes is None
        or len(authoritative_source_codes) != 20
        or len(set(authoritative_source_codes)) != 20
    ):
        blockers.add("ROUND17_ROSTER_ATTESTATION_MISSING")
    elif (
        len(observed_source_codes) != 20
        or set(observed_source_codes) != set(authoritative_source_codes)
    ):
        blockers.add("ROUND17_ROSTER_SOURCE_CODES_MISMATCH")
    if window["roster_version"] != _ROUND17_ROSTER_VERSION:
        blockers.add("ROUND17_ROSTER_VERSION_MISMATCH")
    if window["metric_definition_version"] != _ROUND17_METRIC_DEFINITION_VERSION:
        blockers.add("ROUND17_METRIC_DEFINITION_VERSION_MISMATCH")
    if window["gold_definition_version"] != _ROUND17_GOLD_DEFINITION_VERSION:
        blockers.add("ROUND17_GOLD_DEFINITION_VERSION_MISMATCH")
    if window["database_revision"] != current_database_revision:
        blockers.add("ROUND17_DATABASE_REVISION_MISMATCH")
    return blockers


_Round17ScheduleValues = tuple[int | None, int | None]


def _round17_schedule_values_from_authority(
    poll_interval_minutes: object, document: object
) -> _Round17ScheduleValues:
    """Derive schedule interval from the registry and SLO from approved policy."""

    if (
        isinstance(poll_interval_minutes, bool)
        or not isinstance(poll_interval_minutes, int)
        or not 1 <= poll_interval_minutes <= 10_080
        or not isinstance(document, Mapping)
    ):
        return (None, None)
    slo = document.get("slo")
    if not isinstance(slo, Mapping):
        return (None, None)
    interval_seconds = poll_interval_minutes * 60
    if slo.get("applicability") != "APPLICABLE":
        return (interval_seconds, None)
    target_minutes = slo.get("target_minutes")
    if (
        isinstance(target_minutes, bool)
        or not isinstance(target_minutes, int)
        or not 1 <= target_minutes <= 10_080
    ):
        return (None, None)
    return (interval_seconds, target_minutes * 60)


def _round17_schedule_attestation_blockers(
    observed_schedules: Mapping[str, _Round17ScheduleValues],
    attested_schedules: Mapping[str, tuple[int, int]] | None,
    *,
    authoritative_source_schedules: Mapping[
        str, _Round17ScheduleValues
    ] | None = None,
) -> set[str]:
    """Compare exact schedules with server, registry, and policy authority."""

    blockers: set[str] = set()
    if attested_schedules is None:
        blockers.add("ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISSING")
    elif (
        len(observed_schedules) != 20
        or len(attested_schedules) != 20
        or set(observed_schedules) != set(attested_schedules)
    ):
        blockers.add("ROUND17_SOURCE_SCHEDULE_ATTESTATION_ROSTER_MISMATCH")
    elif any(
        observed_schedules[source_code] != attested_schedules[source_code]
        for source_code in observed_schedules
    ):
        blockers.add("ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISMATCH")

    if authoritative_source_schedules is not None:
        if (
            len(observed_schedules) != 20
            or len(authoritative_source_schedules) != 20
            or set(observed_schedules) != set(authoritative_source_schedules)
        ):
            blockers.add("ROUND17_SOURCE_SCHEDULE_AUTHORITY_ROSTER_MISMATCH")
        elif any(
            observed_schedules[source_code]
            != authoritative_source_schedules[source_code]
            for source_code in observed_schedules
        ):
            blockers.add("ROUND17_SOURCE_SCHEDULE_AUTHORITY_MISMATCH")
    return blockers


def _round17_schedule_write_blockers(
    *,
    source_code: str,
    observed_schedule: tuple[int, int],
    authoritative_source_schedule: _Round17ScheduleValues,
    attested_schedules: Mapping[str, tuple[int, int]] | None,
    authoritative_source_codes: Sequence[str] | None,
) -> set[str]:
    """Protect writes for a configured Round 17 source without changing other cohorts."""

    in_round17_roster = (
        authoritative_source_codes is not None
        and source_code in authoritative_source_codes
    )
    in_schedule_attestation = (
        attested_schedules is not None and source_code in attested_schedules
    )
    if not in_round17_roster and not in_schedule_attestation:
        return set()
    if attested_schedules is None:
        return {"ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISSING"}
    if source_code not in attested_schedules:
        return {"ROUND17_SOURCE_SCHEDULE_ATTESTATION_ROSTER_MISMATCH"}
    blockers: set[str] = set()
    if observed_schedule != attested_schedules[source_code]:
        blockers.add("ROUND17_SOURCE_SCHEDULE_ATTESTATION_MISMATCH")
    if observed_schedule != authoritative_source_schedule:
        blockers.add("ROUND17_SOURCE_SCHEDULE_AUTHORITY_MISMATCH")
    return blockers


async def _gold_sample_is_authoritative(
    connection: AsyncConnection,
    *,
    sample_kind: GoldSampleKind,
    identities: Sequence[UUID],
    source_id: UUID,
) -> bool:
    """Resolve a gold reference only through production, non-fixture authority facts."""

    if sample_kind in {GoldSampleKind.DOCUMENT, GoldSampleKind.PAIR}:
        count = await connection.scalar(
            text(
                """SELECT count(DISTINCT document.id)
                     FROM document document
                     JOIN document_version version
                       ON version.id=document.current_version_id
                    WHERE document.id=ANY(CAST(:identities AS uuid[]))
                      AND document.source_id=:source
                      AND document.admission_fixture=false
                      AND version.execution_domain='PRODUCTION'
                   HAVING count(DISTINCT document.id)=:expected_count"""
            ),
            {
                "identities": list(identities),
                "source": source_id,
                "expected_count": len(identities),
            },
        )
        return int(count or 0) == len(identities)
    if sample_kind is GoldSampleKind.EVENT:
        return bool(
            await connection.scalar(
                text(
                    """SELECT EXISTS (
                         SELECT 1 FROM event event
                        WHERE event.id=:identity
                          AND event.confirmation_status='CONFIRMED'
                          AND EXISTS (
                            SELECT 1 FROM event_item membership
                            JOIN intelligence_item item ON item.id=membership.item_id
                            JOIN document document ON document.id=item.primary_document_id
                            JOIN document_version version
                              ON version.id=item.current_document_version_id
                           WHERE membership.event_id=event.id
                             AND document.source_id=:source
                             AND document.admission_fixture=false
                             AND document.current_version_id=version.id
                             AND version.document_id=document.id
                             AND version.execution_domain='PRODUCTION'
                          )
                          AND NOT EXISTS (
                            SELECT 1 FROM event_item contaminated_membership
                            LEFT JOIN intelligence_item contaminated_item
                              ON contaminated_item.id=contaminated_membership.item_id
                            LEFT JOIN document contaminated_document
                              ON contaminated_document.id=
                                 contaminated_item.primary_document_id
                            LEFT JOIN document_version contaminated_version
                              ON contaminated_version.id=
                                 contaminated_item.current_document_version_id
                           WHERE contaminated_membership.event_id=event.id
                             AND (
                               contaminated_item.id IS NULL
                               OR contaminated_document.id IS NULL
                               OR contaminated_version.id IS NULL
                               OR contaminated_document.source_id<>:source
                               OR contaminated_document.admission_fixture
                               OR contaminated_document.current_version_id
                                    IS DISTINCT FROM contaminated_version.id
                               OR contaminated_version.document_id
                                    IS DISTINCT FROM contaminated_document.id
                               OR contaminated_version.execution_domain<>'PRODUCTION'
                             )
                          )
                       )"""
                ),
                {"identity": identities[0], "source": source_id},
            )
        )
    if sample_kind is GoldSampleKind.CLAIM_EVIDENCE:
        return bool(
            await connection.scalar(
                text(
                    """SELECT EXISTS (
                         SELECT 1 FROM claim claim
                         JOIN claim_evidence evidence
                           ON evidence.id=:evidence AND evidence.claim_id=claim.id
                         JOIN document_version claim_version
                           ON claim_version.id=claim.document_version_id
                         JOIN document claim_document
                           ON claim_document.id=claim_version.document_id
                         JOIN document_version evidence_version
                           ON evidence_version.id=evidence.document_version_id
                         JOIN document evidence_document
                           ON evidence_document.id=evidence_version.document_id
                        WHERE claim.id=:claim
                          AND claim_document.source_id=:source
                          AND evidence_document.source_id=:source
                          AND claim_document.admission_fixture=false
                          AND evidence_document.admission_fixture=false
                          AND claim_version.execution_domain='PRODUCTION'
                          AND evidence_version.execution_domain='PRODUCTION'
                       )"""
                ),
                {
                    "claim": identities[0],
                    "evidence": identities[1],
                    "source": source_id,
                },
            )
        )
    # No approved persisted search-question authority exists yet. Fail closed.
    return False


def _source_supports_gold_domain(content_domains: Sequence[str], domain: str) -> bool:
    authoritative_domains = set(content_domains)
    if domain == "DIGITAL":
        return bool(authoritative_domains & _DIGITAL_SOURCE_CONTENT_DOMAINS)
    if domain == "SAFETY":
        return bool(authoritative_domains & _SAFETY_SOURCE_CONTENT_DOMAINS)
    return False


def _gold_release_sources_match_window(
    release_source_codes: Sequence[str], window_source_codes: Sequence[str]
) -> bool:
    release_codes = set(release_source_codes)
    window_codes = set(window_source_codes)
    return (
        len(release_source_codes) == 20
        and len(window_source_codes) == 20
        and len(release_codes) == 20
        and len(window_codes) == 20
        and release_codes == window_codes
    )


async def _gold_annotation_evidence_is_authoritative(
    connection: AsyncConnection,
    *,
    evidence_ids: Sequence[UUID],
    source_id: UUID,
    sample_kind: GoldSampleKind,
    sample_ref: str,
) -> bool:
    """Accept only current production evidence from accepted claims for the task source."""

    if not evidence_ids:
        return sample_kind is not GoldSampleKind.CLAIM_EVIDENCE
    if len(set(evidence_ids)) != len(evidence_ids):
        return False
    parameters: dict[str, object] = {
        "evidence_ids": list(evidence_ids),
        "source": source_id,
        "expected_count": len(evidence_ids),
    }
    if sample_kind is GoldSampleKind.CLAIM_EVIDENCE:
        _, _, _, claim_text, evidence_text = sample_ref.split(":")
        sample_claim = UUID(claim_text)
        sample_evidence = UUID(evidence_text)
        if tuple(evidence_ids) != (sample_evidence,):
            return False
        parameters.update(
            {"sample_claim": sample_claim, "sample_evidence": sample_evidence}
        )
        statement = text(
            """SELECT count(DISTINCT evidence.id)
                 FROM claim_evidence evidence
                 JOIN claim claim_row ON claim_row.id=evidence.claim_id
                 JOIN document_version claim_version
                   ON claim_version.id=claim_row.document_version_id
                 JOIN document claim_document
                   ON claim_document.id=claim_version.document_id
                 JOIN document_version evidence_version
                   ON evidence_version.id=evidence.document_version_id
                 JOIN document evidence_document
                   ON evidence_document.id=evidence_version.document_id
                WHERE evidence.id=ANY(CAST(:evidence_ids AS uuid[]))
                  AND evidence.id=:sample_evidence AND claim_row.id=:sample_claim
                  AND claim_row.verification_status='ACCEPTED'
                  AND claim_document.source_id=:source
                  AND evidence_document.source_id=:source
                  AND claim_document.admission_fixture=false
                  AND evidence_document.admission_fixture=false
                  AND claim_document.current_version_id=claim_version.id
                  AND evidence_document.current_version_id=evidence_version.id
                  AND claim_version.execution_domain='PRODUCTION'
                  AND evidence_version.execution_domain='PRODUCTION'
               HAVING count(DISTINCT evidence.id)=:expected_count"""
        )
    else:
        statement = text(
            """SELECT count(DISTINCT evidence.id)
                 FROM claim_evidence evidence
                 JOIN claim claim_row ON claim_row.id=evidence.claim_id
                 JOIN document_version claim_version
                   ON claim_version.id=claim_row.document_version_id
                 JOIN document claim_document
                   ON claim_document.id=claim_version.document_id
                 JOIN document_version evidence_version
                   ON evidence_version.id=evidence.document_version_id
                 JOIN document evidence_document
                   ON evidence_document.id=evidence_version.document_id
                WHERE evidence.id=ANY(CAST(:evidence_ids AS uuid[]))
                  AND claim_row.verification_status='ACCEPTED'
                  AND claim_document.source_id=:source
                  AND evidence_document.source_id=:source
                  AND claim_document.admission_fixture=false
                  AND evidence_document.admission_fixture=false
                  AND claim_document.current_version_id=claim_version.id
                  AND evidence_document.current_version_id=evidence_version.id
                  AND claim_version.execution_domain='PRODUCTION'
                  AND evidence_version.execution_domain='PRODUCTION'
               HAVING count(DISTINCT evidence.id)=:expected_count"""
        )
    count = await connection.scalar(statement, parameters)
    return int(count or 0) == len(evidence_ids)


def _gold_manifest_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    """Hash a stable, order-independent release manifest."""

    normalized = sorted(
        (dict(record) for record in records),
        key=lambda record: json.dumps(
            record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ),
    )
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _gold_agreement_metrics(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, float | int | str]:
    """Recompute raw agreement and nominal Gwet AC1 from blinded label signatures."""

    by_task: dict[str, list[str]] = {}
    for record in records:
        by_task.setdefault(str(record["task_id"]), []).append(str(record["signature"]))
    pairs = [values for values in by_task.values() if len(values) == 2]
    if not pairs:
        return {
            "double_labeled_count": 0,
            "raw_agreement": 0.0,
            "coefficient_name": "GWET_AC1",
            "coefficient": 0.0,
        }
    observed = sum(1 for left, right in pairs if left == right) / len(pairs)
    labels = [label for pair in pairs for label in pair]
    categories = sorted(set(labels))
    if len(categories) <= 1:
        chance = 0.0
    else:
        chance = sum(
            (labels.count(category) / len(labels))
            * (1 - labels.count(category) / len(labels))
            for category in categories
        ) / (len(categories) - 1)
    coefficient = 1.0 if observed == 1.0 else (observed - chance) / (1 - chance)
    return {
        "double_labeled_count": len(pairs),
        "raw_agreement": round(observed, 6),
        "coefficient_name": "GWET_AC1",
        "coefficient": round(coefficient, 6),
    }


def _bounded_active_seconds(started_at: datetime, stopped_at: datetime) -> int:
    """Bound one uninterrupted timer segment to the 15-minute inactivity limit."""

    elapsed = max(0, int((stopped_at - started_at).total_seconds()))
    return min(elapsed, 15 * 60)


def _pilot_window_view(row: Mapping[str, Any] | RowMapping) -> PilotWindowView:
    return PilotWindowView(
        id=row["id"],
        roster_version=row["roster_version"],
        metric_definition_version=row["metric_definition_version"],
        gold_definition_version=row["gold_definition_version"],
        baseline_commit=row["baseline_commit"],
        config_version=row["config_version"],
        database_revision=row["database_revision"],
        environment=row["environment"],
        duration_hours=row["duration_hours"],
        source_count=row["source_count"],
        state=PilotWindowState(row["state"]),
        version=row["version"],
        prepared_at=row["prepared_at"],
        started_at=row["started_at"],
        ends_at=row["ends_at"],
        blocker_codes=list(row["blocker_codes"] or ()),
    )


def _gold_task_view(row: Mapping[str, Any] | RowMapping) -> GoldTaskView:
    return GoldTaskView(
        id=row["id"],
        sample_kind=GoldSampleKind(row["sample_kind"]),
        sample_ref=row["sample_ref"],
        source_code=row["source_code"],
        domain=row["domain"],
        production_decision_id=row["production_decision_id"],
        critical_safety=row["critical_safety"],
        secondary_review_required=row["secondary_review_required"],
        status=row["status"],
        assigned_at=row["assigned_at"],
    )


def _gold_annotation_view(row: Mapping[str, Any] | RowMapping) -> GoldAnnotationView:
    return GoldAnnotationView(
        id=row["id"],
        task_id=row["task_id"],
        annotator_id=row["annotator_id"],
        sample_kind=GoldSampleKind(row["sample_kind"]),
        decision_code=row["decision_code"],
        submitted_at=row["submitted_at"],
        status=row["status"],
    )


def _work_session_view(row: Mapping[str, Any] | RowMapping) -> OperatorWorkSessionView:
    return OperatorWorkSessionView(
        id=row["id"],
        task_id=row["task_id"],
        window_id=row["window_id"],
        actor_id=row["actor_id"],
        category=OperatorWorkCategory(row["category"]),
        started_at=row["started_at"],
        last_activity_at=row["last_activity_at"],
        stopped_at=row["stopped_at"],
        active_seconds=row["active_seconds"],
        corrected=row["corrected"],
        version=row["version"],
    )


def _operator_task_view(row: Mapping[str, Any] | RowMapping) -> OperatorTaskView:
    return OperatorTaskView(
        id=row["id"],
        window_id=row["window_id"],
        source_id=row["source_id"],
        category=OperatorWorkCategory(row["category"]),
        assigned_to=row["assigned_to"],
        status=OperatorTaskStatus(row["status"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_by=row["completed_by"],
        completed_at=row["completed_at"],
        version=row["version"],
    )


def _schedule_view(row: Mapping[str, Any] | RowMapping) -> FetchScheduleView:
    return FetchScheduleView(
        source_id=row["source_id"],
        authority_level=row["authority_level"],
        status=FetchScheduleStatus(row["status"]),
        interval_seconds=row["interval_seconds"],
        next_run_at=row["next_run_at"],
        circuit_state=CircuitState(row["circuit_state"]),
        circuit_open_until=row["circuit_open_until"],
        consecutive_failures=row["consecutive_failures"],
        freshness_slo_seconds=row["freshness_slo_seconds"],
        rate_limit_per_minute=row["rate_limit_per_minute"],
        daily_request_budget=row["daily_request_budget"],
        daily_byte_budget=row["daily_byte_budget"],
        requests_used=row["requests_used"],
        bytes_used=row["bytes_used"],
        version=row["version"],
        updated_at=row["updated_at"],
    )


class PostgresOperationsService:
    def __init__(
        self,
        engine: AsyncEngine,
        projection_engine: AsyncEngine | None = None,
        now: Callable[[], datetime] | None = None,
        *,
        environment: str = "demo",
        ai_enabled: bool = False,
        semantic_search_enabled: bool = False,
        external_notifications_enabled: bool = False,
        round17_baseline_commit_attestation: str | None = None,
        round17_config_version_attestation: str | None = None,
        round17_roster_source_codes: Sequence[str] | None = None,
        round17_source_schedule_attestations: Mapping[
            str, tuple[int, int]
        ] | None = None,
        round17_leo_approver_actor_id: UUID | None = None,
        round17_eventization_trusted_public_key_base64: str | None = None,
        round17_eventization_trusted_public_key_sha256: str | None = None,
    ) -> None:
        self._engine = engine
        self._projection_engine = projection_engine
        self._now = now or (lambda: datetime.now(UTC))
        self._environment = environment.casefold()
        self._ai_enabled = ai_enabled
        self._semantic_search_enabled = semantic_search_enabled
        self._external_notifications_enabled = external_notifications_enabled
        self._round17_baseline_commit_attestation = round17_baseline_commit_attestation
        self._round17_config_version_attestation = round17_config_version_attestation
        self._round17_roster_source_codes = (
            tuple(round17_roster_source_codes)
            if round17_roster_source_codes is not None
            else None
        )
        self._round17_source_schedule_attestations = (
            dict(round17_source_schedule_attestations)
            if round17_source_schedule_attestations is not None
            else None
        )
        self._round17_leo_approver_actor_id = round17_leo_approver_actor_id
        self._round17_eventization_trusted_public_key_base64 = (
            round17_eventization_trusted_public_key_base64
        )
        self._round17_eventization_trusted_public_key_sha256 = (
            round17_eventization_trusted_public_key_sha256
        )

    def _require_round17_leo_actor(self, actor_id: UUID) -> None:
        if not _round17_leo_actor_is_attested(
            actor_id, self._round17_leo_approver_actor_id
        ):
            raise OperationsRejected("Round 17 action requires the sole attested LEO actor")

    async def close(self) -> None:
        await self._engine.dispose()
        if self._projection_engine is not None:
            await self._projection_engine.dispose()

    async def round17_observability(self) -> dict[str, object]:
        """Return bounded database-derived pilot gauges without source or actor labels."""

        async with self._engine.connect() as connection:
            window_rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT state,count(*) AS count FROM round17_pilot_window "
                            "GROUP BY state"
                        )
                    )
                )
                .mappings()
                .all()
            )
            source_rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT status,count(*) AS count "
                            "FROM round17_pilot_window_source GROUP BY status"
                        )
                    )
                )
                .mappings()
                .all()
            )
            contaminated_runs = await connection.scalar(
                text(
                    """SELECT count(*) FROM fetch_run
                        WHERE pilot_window_source_id IS NOT NULL
                          AND (run_origin<>'SCHEDULED' OR execution_domain<>'PRODUCTION')"""
                )
            )
            stale_work_timers = await connection.scalar(
                text(
                    """SELECT count(*) FROM round17_operator_work_session
                        WHERE stopped_at IS NULL
                          AND last_activity_at < now() - interval '15 minutes'"""
                )
            )
        return {
            "window_states": {str(row["state"]): int(row["count"]) for row in window_rows},
            "source_states": {str(row["status"]): int(row["count"]) for row in source_rows},
            "contaminated_runs": int(contaminated_runs or 0),
            "stale_work_timers": int(stale_work_timers or 0),
        }

    async def overview(self) -> OperationsOverview:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT
                          (SELECT count(*) FROM source_checkpoint
                             WHERE consecutive_failures > 0) AS unhealthy_sources,
                          (SELECT count(*) FROM source_checkpoint
                             WHERE circuit_open_until > now()) AS open_circuits,
                          (SELECT count(*) FROM review_task
                            WHERE status = 'PENDING') AS pending_reviews,
                          (SELECT count(*) FROM outbox_event
                            WHERE processed_at IS NULL) AS outbox_depth,
                          (SELECT count(*) FROM failed_task
                            WHERE resolved_at IS NULL) AS failed_tasks,
                          (SELECT count(*) FROM replay_request
                            WHERE status = 'QUEUED') AS queued_replays,
                          (SELECT COALESCE(EXTRACT(epoch FROM now() - min(started_at)), 0)
                             FROM fetch_run
                            WHERE status IN (
                              'PENDING_DISPATCH','DISPATCHED','RETRY_WAIT'
                            ))
                             AS fetch_backlog_age_seconds,
                          (SELECT count(*) FROM source_health_snapshot
                             WHERE freshness_status='VIOLATED' OR discovery_status='FALSE_SUCCESS')
                             AS source_slo_violations,
                          (SELECT count(*) FROM failed_task WHERE resolved_at IS NULL
                             AND reconstruction_status IN ('BLOCKED','NON_REPLAYABLE'))
                             AS blocked_replays,
                          (SELECT count(*) FROM retention_execution WHERE status='FAILED')
                             AS retention_failures,
                          (SELECT count(*) FROM ai_step_run
                            WHERE status = 'FAILED'
                              AND created_at >= now() - interval '24 hours') AS ai_failures,
                          (SELECT COALESCE(sum(cost_microusd), 0) FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_cost,
                          (SELECT COALESCE(percentile_cont(0.95) WITHIN GROUP
                              (ORDER BY latency_ms), 0) FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_p95_ms,
                          (SELECT COALESCE(sum(cost_microusd) /
                              NULLIF(count(DISTINCT pipeline_run_id), 0), 0)
                             FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_doc_cost
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )
        metrics = [
            MetricSample(
                code="UNHEALTHY_SOURCES",
                value=row["unhealthy_sources"],
                unit="count",
                status="PASS" if row["unhealthy_sources"] == 0 else "FAIL",
            ),
            MetricSample(
                code="OPEN_SOURCE_CIRCUITS",
                value=row["open_circuits"],
                unit="count",
                status="PASS" if row["open_circuits"] == 0 else "FAIL",
            ),
            MetricSample(
                code="PENDING_REVIEWS", value=row["pending_reviews"], unit="count", status="UNKNOWN"
            ),
            MetricSample(
                code="PUBLISHER_OUTBOX_DEPTH",
                value=row["outbox_depth"],
                unit="count",
                status="PASS" if row["outbox_depth"] == 0 else "UNKNOWN",
            ),
            MetricSample(
                code="FAILED_TASKS",
                value=row["failed_tasks"],
                unit="count",
                status="PASS" if row["failed_tasks"] == 0 else "FAIL",
            ),
            MetricSample(
                code="QUEUED_REPLAYS", value=row["queued_replays"], unit="count", status="UNKNOWN"
            ),
            MetricSample(
                code="FETCH_BACKLOG_AGE_SECONDS",
                value=float(row["fetch_backlog_age_seconds"]),
                unit="seconds",
                status="PASS" if row["fetch_backlog_age_seconds"] <= 900 else "FAIL",
            ),
            MetricSample(
                code="SOURCE_SLO_VIOLATIONS",
                value=row["source_slo_violations"],
                unit="count",
                status="PASS" if row["source_slo_violations"] == 0 else "FAIL",
            ),
            MetricSample(
                code="BLOCKED_REPLAYS",
                value=row["blocked_replays"],
                unit="count",
                status="PASS" if row["blocked_replays"] == 0 else "FAIL",
            ),
            MetricSample(
                code="RETENTION_FAILURES",
                value=row["retention_failures"],
                unit="count",
                status="PASS" if row["retention_failures"] == 0 else "FAIL",
            ),
            MetricSample(
                code="AI_FAILURES_24H",
                value=row["ai_failures"],
                unit="count",
                status="PASS" if row["ai_failures"] == 0 else "FAIL",
            ),
            MetricSample(
                code="AI_COST_MICROUSD_24H",
                value=int(row["ai_cost"]),
                unit="microusd",
                status="UNKNOWN",
            ),
            MetricSample(
                code="AI_LATENCY_P95_MS_24H",
                value=float(row["ai_p95_ms"]),
                unit="ms",
                status="UNKNOWN",
            ),
            MetricSample(
                code="AI_COST_PER_DOCUMENT_MICROUSD_24H",
                value=int(row["ai_doc_cost"]),
                unit="microusd",
                status="UNKNOWN",
            ),
        ]
        return OperationsOverview(observed_at=self._now(), metrics=metrics)

    async def request_replay(
        self,
        payload: ReplayRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> ReplayResult:
        now = self._now()
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """SELECT r.id, r.failed_task_id, f.task_kind, r.priority, r.status
                           FROM replay_request r JOIN failed_task f ON f.id = r.failed_task_id
                          WHERE r.idempotency_key = :key"""
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return ReplayResult.model_validate(existing)
            failed = (
                (
                    await connection.execute(
                        text(
                            """SELECT id, task_kind FROM failed_task
                            WHERE id = :failed_task_id
                              AND replayable IS TRUE
                              AND resolved_at IS NULL
                              AND (reconstruction_status='REPLAYABLE'
                                   OR task_kind IN ('PUBLICATION_OUTBOX','PROJECTION'))
                            """
                        ),
                        {"failed_task_id": payload.failed_task_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if failed is None:
                raise OperationsRejected("only an unresolved failed task may be replayed")
            replay_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO replay_request
                       (id, failed_task_id, actor_id, reason, priority,
                        idempotency_key, status, requested_at)
                       VALUES (:id, :failed, :actor, :reason, :priority, :key, 'QUEUED', :now)"""
                ),
                {
                    "id": replay_id,
                    "failed": failed["id"],
                    "actor": actor_id,
                    "reason": payload.reason,
                    "priority": payload.priority,
                    "key": idempotency_key,
                    "now": now,
                },
            )
        return ReplayResult(
            id=replay_id,
            failed_task_id=payload.failed_task_id,
            task_kind=str(failed["task_kind"]),
            priority=payload.priority,
            status="QUEUED",
        )

    async def get_schedule(self, source_id: UUID) -> FetchScheduleView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE source_id=:source_id"),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OperationsRejected("source schedule does not exist")
        return _schedule_view(row)

    async def update_schedule(
        self,
        source_id: UUID,
        payload: FetchScheduleUpdate,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView:
        now = self._now()
        async with self._engine.begin() as connection:
            source = (
                (
                    await connection.execute(
                        text(
                            """SELECT s.registry_code,s.authority_level, s.lifecycle_state,
                                  s.poll_interval_minutes,
                                  p.status AS policy_status, p.valid_from, p.valid_until,
                                  p.document AS policy_document,
                                  COALESCE(
                                    (p.document #>> '{fetch,rate_limit_per_minute}')::int,
                                    1
                                  ) AS policy_rate
                           FROM source s JOIN source_policy_version p
                             ON p.id=s.current_policy_version_id
                           WHERE s.id=:source_id FOR UPDATE"""
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source is None:
                raise OperationsRejected("source or current policy does not exist")
            if (
                source["lifecycle_state"] != "ACTIVE"
                or source["policy_status"] != "APPROVED"
                or source["valid_from"] > now
                or source["valid_until"] <= now
            ):
                raise OperationsRejected(
                    "only an ACTIVE source with a valid policy may be scheduled"
                )
            if payload.interval_seconds < int(source["poll_interval_minutes"]) * 60:
                raise OperationsRejected(
                    "schedule is more frequent than the approved source interval"
                )
            if payload.rate_limit_per_minute > int(source["policy_rate"]):
                raise OperationsRejected("schedule rate exceeds the approved source policy")
            round17_schedule_blockers = _round17_schedule_write_blockers(
                source_code=str(source["registry_code"]),
                observed_schedule=(
                    payload.interval_seconds,
                    payload.freshness_slo_seconds,
                ),
                authoritative_source_schedule=_round17_schedule_values_from_authority(
                    source["poll_interval_minutes"], source["policy_document"]
                ),
                attested_schedules=self._round17_source_schedule_attestations,
                authoritative_source_codes=self._round17_roster_source_codes,
            )
            if round17_schedule_blockers:
                raise OperationsRejected(
                    "Round 17 schedule write authority mismatch: "
                    + ", ".join(sorted(round17_schedule_blockers))
                )
            existing = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE source_id=:source_id FOR UPDATE"),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None and payload.expected_version != 0:
                raise OperationsRejected("schedule version conflict")
            if existing is not None and existing["last_idempotency_key"] == idempotency_key:
                return _schedule_view(existing)
            if existing is not None and existing["version"] != payload.expected_version:
                raise OperationsRejected("schedule version conflict")
            schedule_id = uuid7() if existing is None else existing["id"]
            next_run_at = now if existing is None else existing["next_run_at"]
            await connection.execute(
                text(
                    """INSERT INTO fetch_schedule
                       (id,source_id,authority_level,status,interval_seconds,next_run_at,
                        backoff_base_seconds,backoff_cap_seconds,max_attempts,consecutive_failures,
                        circuit_state,freshness_slo_seconds,rate_limit_per_minute,
                        daily_request_budget,daily_byte_budget,requests_used,bytes_used,
                        budget_window_started_at,version,last_idempotency_key,updated_at)
                       VALUES (:id,:source,:authority,:status,:interval,:next_run,30,21600,3,0,
                               'CLOSED',:slo,:rate,:request_budget,:byte_budget,0,0,:now,1,:key,:now)
                       ON CONFLICT (source_id) DO UPDATE SET
                         status=EXCLUDED.status, interval_seconds=EXCLUDED.interval_seconds,
                         freshness_slo_seconds=EXCLUDED.freshness_slo_seconds,
                         rate_limit_per_minute=EXCLUDED.rate_limit_per_minute,
                         daily_request_budget=EXCLUDED.daily_request_budget,
                         daily_byte_budget=EXCLUDED.daily_byte_budget,
                         last_idempotency_key=EXCLUDED.last_idempotency_key,
                         version=fetch_schedule.version+1, updated_at=EXCLUDED.updated_at"""
                ),
                {
                    "id": schedule_id,
                    "source": source_id,
                    "authority": source["authority_level"],
                    "status": payload.status.value,
                    "interval": payload.interval_seconds,
                    "next_run": next_run_at,
                    "slo": payload.freshness_slo_seconds,
                    "rate": payload.rate_limit_per_minute,
                    "request_budget": payload.daily_request_budget,
                    "byte_budget": payload.daily_byte_budget,
                    "key": idempotency_key,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event("
                    ":id,'FETCH_SCHEDULE_UPDATED',:actor,'fetch_schedule',:target,NULL,"
                    "jsonb_build_object('source_id',:source,'status',:status,"
                    "'idempotency_key',:key),"
                    ":reason,:key,:now)"
                ),
                {
                    "id": uuid7(),
                    "actor": actor_id,
                    "target": schedule_id,
                    "source": str(source_id),
                    "status": payload.status.value,
                    "key": idempotency_key,
                    "reason": payload.reason,
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE id=:id"), {"id": schedule_id}
                    )
                )
                .mappings()
                .one()
            )
        return _schedule_view(row)

    async def source_health(self) -> list[SourceHealthView]:
        async with self._engine.connect() as connection:
            snapshots = (
                (
                    await connection.execute(
                        text(
                            """SELECT DISTINCT ON (source_id) * FROM source_health_snapshot
                           ORDER BY source_id, observed_at DESC"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            anomalies = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,source_id,code,severity,status,detected_at "
                            "FROM source_anomaly WHERE status <> 'RESOLVED' "
                            "ORDER BY detected_at DESC"
                        )
                    )
                )
                .mappings()
                .all()
            )
        by_source: dict[UUID, list[SourceAnomalyView]] = {}
        for anomaly in anomalies:
            by_source.setdefault(anomaly["source_id"], []).append(
                SourceAnomalyView.model_validate(anomaly)
            )
        return [
            SourceHealthView(
                source_id=row["source_id"],
                fetch_run_id=row["fetch_run_id"],
                transport_status=row["transport_status"],
                discovery_status=row["discovery_status"],
                parse_status=row["parse_status"],
                quality_status=row["quality_status"],
                freshness_status=row["freshness_status"],
                rule_version=row["rule_version"],
                observed_at=row["observed_at"],
                anomalies=by_source.get(row["source_id"], []),
            )
            for row in snapshots
        ]

    async def list_replays(self) -> list[ReplayTaskView]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT f.id,f.task_kind,f.error_code,f.priority,
                                  f.reconstruction_status,f.blocked_reason,f.source_id,f.run_id,
                                  f.document_version_id,f.event_id,f.failed_at,
                                  r.status AS replay_status
                           FROM failed_task f LEFT JOIN LATERAL (
                             SELECT status FROM replay_request rr WHERE rr.failed_task_id=f.id
                             ORDER BY requested_at DESC LIMIT 1
                           ) r ON TRUE WHERE f.resolved_at IS NULL
                           ORDER BY f.priority DESC,f.failed_at"""
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [ReplayTaskView.model_validate(row) for row in rows]

    async def record_feedback(
        self,
        *,
        item_id: UUID | None,
        event_id: UUID | None = None,
        value: str,
        actor_id: UUID,
    ) -> None:
        now = self._now()
        if event_id is not None:
            if self._projection_engine is None:
                raise OperationsRejected("published Event projection is unavailable")
            async with self._projection_engine.connect() as projection_connection:
                visible = await projection_connection.scalar(
                    text(
                        "SELECT 1 FROM published_v1.current_event_summary WHERE event_id=:event_id"
                    ),
                    {"event_id": event_id},
                )
            if visible is None:
                raise OperationsRejected("feedback target is not visible")
        async with self._engine.begin() as connection:
            if event_id is not None:
                switch = await connection.scalar(
                    text("SELECT status FROM event_consumer_switch WHERE singleton")
                )
                if switch != "EVENT":
                    raise OperationsRejected("event consumer writes are read-only")
            elif item_id is None:
                raise OperationsRejected("feedback target is not visible")
            else:
                visible = (
                    await connection.execute(
                        text(
                            """SELECT 1 FROM publication
                                WHERE item_id = :item_id AND status = 'PUBLISHED'"""
                        ),
                        {"item_id": item_id},
                    )
                ).scalar_one_or_none()
                if visible is None:
                    raise OperationsRejected("feedback target is not visible")
            await connection.execute(
                text(
                    """INSERT INTO item_feedback
                         (id, actor_id, item_id, event_id, value, recorded_at)
                       VALUES (:id, :actor, :item, :event, :value, :now)
                       ON CONFLICT (actor_id, event_id) DO UPDATE
                       SET value = EXCLUDED.value, recorded_at = EXCLUDED.recorded_at"""
                ),
                {
                    "id": uuid7(),
                    "actor": actor_id,
                    "item": None if event_id is not None else item_id,
                    "event": event_id,
                    "value": value,
                    "now": now,
                },
            )

    async def record_usage(
        self,
        *,
        event_type: str,
    ) -> None:
        allowed = {"SEARCH", "VIEW_EVIDENCE", "SAVE_ITEM", "EXPORT", "READ_DAILY"}
        if event_type not in allowed:
            raise OperationsRejected("usage event type is not permitted")
        bucket_started_at = self._now().replace(minute=0, second=0, microsecond=0)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO usage_metric_bucket
                       (id, event_type, bucket_started_at, event_count)
                       VALUES (:id, :event_type, :bucket_started_at, 1)
                       ON CONFLICT (event_type, bucket_started_at) DO UPDATE
                       SET event_count = usage_metric_bucket.event_count + 1"""
                ),
                {
                    "id": uuid7(),
                    "event_type": event_type,
                    "bucket_started_at": bucket_started_at,
                },
            )

    async def pilot_metrics(self) -> PilotMetrics:
        now = self._now()
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """SELECT
                          COALESCE(min(bucket_started_at), :now) AS started_at,
                          COALESCE(max(bucket_started_at), :now) AS ended_at,
                          COALESCE(sum(event_count), 0) AS aggregate_actions
                          FROM usage_metric_bucket"""
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .one()
            )
            votes = (
                (
                    await connection.execute(
                        text(
                            """SELECT count(*) FILTER (WHERE value='USEFUL') AS useful,
                                  count(*) AS total,
                                  count(DISTINCT actor_id) AS feedback_users
                                  FROM item_feedback"""
                        ),
                    )
                )
                .mappings()
                .one()
            )
        return PilotMetrics(
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            aggregate_effective_actions=row["aggregate_actions"],
            distinct_feedback_users=votes["feedback_users"],
            useful_votes=votes["useful"],
            total_votes=votes["total"],
            identity_metrics_available=False,
            sufficient_window=False,
        )

    async def prepare_pilot_window(
        self,
        payload: PilotWindowCreateRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        """Pin a candidate cohort without activating or approving any source."""

        now = self._now()
        window_id = uuid7()
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source segment
                                        WHERE segment.window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row
                                WHERE window_row.idempotency_key=:key"""
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return _pilot_window_view(existing)

            database_revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            if database_revision != payload.database_revision:
                raise OperationsRejected("database revision does not match the running schema")

            await connection.execute(
                text(
                    """INSERT INTO round17_pilot_window (
                         id,roster_version,metric_definition_version,gold_definition_version,
                         baseline_commit,config_version,database_revision,environment,
                         duration_hours,state,version,blocker_codes,prepared_by,prepared_at,
                         idempotency_key
                       ) VALUES (
                         :id,:roster,:metric,:gold,:commit,:config,:database_revision,
                         'PREPRODUCTION',168,'PREPARING',1,'{}'::text[],:actor,:now,:key
                       )"""
                ),
                {
                    "id": window_id,
                    "roster": payload.roster_version,
                    "metric": payload.metric_definition_version,
                    "gold": payload.gold_definition_version,
                    "commit": payload.baseline_commit,
                    "config": payload.config_version,
                    "database_revision": payload.database_revision,
                    "actor": actor_id,
                    "now": now,
                    "key": idempotency_key,
                },
            )
            source_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT s.id,s.registry_code,s.lifecycle_state,
                                      s.poll_interval_minutes,
                                      s.current_policy_version_id AS policy_id,
                                      s.current_connector_config_version_id AS config_id,
                                      s.current_trial_run_id AS trial_id,
                                      schedule.id AS schedule_id,
                                      schedule.version AS schedule_version,
                                      schedule.interval_seconds,
                                      schedule.freshness_slo_seconds,
                                      policy.document AS policy_document,
                                      decision.id AS production_decision_id,
                                      readiness.id AS eventization_readiness_id,
                                      to_jsonb(readiness) AS eventization_readiness
                                 FROM source s
                                 LEFT JOIN source_policy_version policy
                                   ON policy.id=s.current_policy_version_id
                                 LEFT JOIN fetch_schedule schedule ON schedule.source_id=s.id
                                 LEFT JOIN LATERAL (
                                   SELECT d.id
                                     FROM source_governance_decision d
                                    WHERE d.source_id=s.id
                                      AND d.decision_type='PRODUCTION_APPROVAL'
                                      AND d.outcome='APPROVED'
                                    ORDER BY d.created_at DESC,d.id DESC LIMIT 1
                                 ) decision ON true
                                 LEFT JOIN round17_eventization_readiness readiness
                                   ON readiness.source_id=s.id
                                  AND readiness.policy_version_id=
                                      s.current_policy_version_id
                                  AND readiness.connector_config_version_id=
                                      s.current_connector_config_version_id
                                  AND readiness.trial_run_id=s.current_trial_run_id
                                  AND readiness.production_decision_id=decision.id
                                  AND readiness.status='PASSED'
                                WHERE s.registry_code=ANY(CAST(:codes AS text[]))
                                ORDER BY s.registry_code"""
                        ),
                        {"codes": payload.source_codes},
                    )
                )
                .mappings()
                .all()
            )
            found_codes = {str(row["registry_code"]) for row in source_rows}
            blockers: set[str] = set()
            if found_codes != set(payload.source_codes) or len(source_rows) != 20:
                blockers.add("SOURCE_COHORT_NOT_EXACTLY_20")
            observed_schedules: dict[str, _Round17ScheduleValues] = {
                str(row["registry_code"]): (
                    int(row["interval_seconds"])
                    if row["interval_seconds"] is not None
                    else None,
                    int(row["freshness_slo_seconds"])
                    if row["freshness_slo_seconds"] is not None
                    else None,
                )
                for row in source_rows
            }
            authoritative_source_schedules = {
                str(row["registry_code"]): _round17_schedule_values_from_authority(
                    row["poll_interval_minutes"], row["policy_document"]
                )
                for row in source_rows
            }
            blockers.update(
                _round17_schedule_attestation_blockers(
                    observed_schedules,
                    self._round17_source_schedule_attestations,
                    authoritative_source_schedules=authoritative_source_schedules,
                )
            )
            for row in source_rows:
                if row["lifecycle_state"] != "ACTIVE":
                    blockers.add("SOURCE_NOT_ACTIVE")
                if row["policy_id"] is None:
                    blockers.add("SOURCE_POLICY_NOT_APPROVED")
                if row["config_id"] is None:
                    blockers.add("SOURCE_CONNECTOR_NOT_CURRENT")
                if row["trial_id"] is None:
                    blockers.add("LIVE_TRIAL_NOT_SUCCEEDED")
                if row["production_decision_id"] is None:
                    blockers.add("PRODUCTION_APPROVAL_NOT_CURRENT")
                if row["schedule_id"] is None:
                    blockers.add("SOURCE_SCHEDULE_NOT_ACTIVE")
                eventization_readiness = row["eventization_readiness"]
                if row["eventization_readiness_id"] is None or not isinstance(
                    eventization_readiness, dict
                ) or not _eventization_manifest_is_trusted(
                    eventization_readiness,
                    source_code=str(row["registry_code"]),
                    leo_actor_id=self._round17_leo_approver_actor_id,
                    trusted_public_key_base64=(
                        self._round17_eventization_trusted_public_key_base64
                    ),
                    trusted_public_key_sha256=(
                        self._round17_eventization_trusted_public_key_sha256
                    ),
                ):
                    blockers.add("SOURCE_EVENTIZATION_PIPELINE_NOT_READY")
                await connection.execute(
                    text(
                        """INSERT INTO round17_pilot_window_source (
                             id,window_id,source_id,source_code,policy_version_id,
                             connector_config_version_id,schedule_id,trial_run_id,
                             schedule_version,interval_seconds,freshness_slo_seconds,
                             production_decision_id,eventization_readiness_id,
                             segment_number,status,created_at
                           ) VALUES (
                             :id,:window,:source,:code,:policy,:config,:schedule,:trial,
                             :schedule_version,:interval,:slo,:decision,:readiness,
                             1,'PREPARING',:now
                           )"""
                    ),
                    {
                        "id": uuid7(),
                        "window": window_id,
                        "source": row["id"],
                        "code": row["registry_code"],
                        "policy": row["policy_id"],
                        "config": row["config_id"],
                        "schedule": row["schedule_id"],
                        "trial": row["trial_id"],
                        "schedule_version": row["schedule_version"],
                        "interval": row["interval_seconds"],
                        "slo": row["freshness_slo_seconds"],
                        "decision": row["production_decision_id"],
                        "readiness": row["eventization_readiness_id"],
                        "now": now,
                    },
                )
            state = "READY" if not blockers else "BLOCKED"
            await connection.execute(
                text(
                    """UPDATE round17_pilot_window
                          SET state=:state,version=version+1,blocker_codes=:blockers
                        WHERE id=:id"""
                ),
                {"id": window_id, "state": state, "blockers": sorted(blockers)},
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_WINDOW_PREPARED',:actor,"
                    "'ROUND17_PILOT_WINDOW',:window,NULL,"
                    "jsonb_build_object('state',:state,'source_count',:source_count),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "window": window_id,
                    "state": state,
                    "source_count": len(source_rows),
                    "reason": payload.reason,
                    "request_id": idempotency_key,
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source
                                        WHERE window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row WHERE id=:id"""
                        ),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one()
            )
        return _pilot_window_view(row)

    async def list_pilot_windows(self) -> list[PilotWindowView]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source segment
                                        WHERE segment.window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row
                                ORDER BY prepared_at DESC,id DESC"""
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [_pilot_window_view(row) for row in rows]

    async def start_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowStartRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        """Re-evaluate all authoritative facts at T0 and fail closed."""

        self._require_round17_leo_actor(actor_id)
        now = self._now()
        async with self._engine.begin() as connection:
            window = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_pilot_window WHERE id=:id FOR UPDATE"),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if window is None:
                raise OperationsRejected("pilot window does not exist")
            if window["state"] == "RUNNING":
                row = dict(window)
                row["source_count"] = await connection.scalar(
                    text(
                        "SELECT count(DISTINCT source_id) FROM round17_pilot_window_source "
                        "WHERE window_id=:id"
                    ),
                    {"id": window_id},
                )
                return _pilot_window_view(row)
            if window["state"] not in {"READY", "BLOCKED"} or window["started_at"] is not None:
                raise OperationsRejected("pilot window state cannot be restarted")
            if window["version"] != payload.expected_version:
                raise OperationsRejected("pilot window version conflict")

            locked_schedule_ids = tuple(
                (
                    await connection.execute(
                        text(
                            """SELECT schedule.id
                                 FROM round17_pilot_window_source segment
                                 JOIN fetch_schedule schedule
                                   ON schedule.id=segment.schedule_id
                                WHERE segment.window_id=:window
                                  AND segment.segment_number=1
                                ORDER BY segment.source_code
                                FOR UPDATE OF schedule"""
                        ),
                        {"window": window_id},
                    )
                ).scalars()
            )
            source_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT segment.source_code,segment.schedule_id AS pinned_schedule_id,
                                      schedule.interval_seconds AS current_interval_seconds,
                                      schedule.freshness_slo_seconds
                                        AS current_freshness_slo_seconds,
                                      p.document AS policy_document,
                                      s.poll_interval_minutes,
                                      s.lifecycle_state,
                                      p.status AS policy_status,
                                      LEAST(p.valid_until,COALESCE(decision.valid_until,p.valid_until))
                                        AS approval_valid_until,
                                      (s.current_policy_version_id=segment.policy_version_id
                                       AND s.current_connector_config_version_id=
                                           segment.connector_config_version_id)
                                        AS connector_current,
                                      (trial.kind='LIVE_TRIAL' AND trial.execution_domain='TRIAL'
                                       AND result.status='SUCCEEDED') AS live_trial_succeeded,
                                      (decision.id=segment.production_decision_id
                                       AND decision.outcome='APPROVED'
                                       AND decision.policy_version_id=segment.policy_version_id
                                       AND decision.connector_config_version_id=
                                           segment.connector_config_version_id
                                       AND decision.trial_run_id=segment.trial_run_id)
                                        AS production_approval_current,
                                      (schedule.id=segment.schedule_id
                                       AND schedule.status='ACTIVE'
                                       AND schedule.version=segment.schedule_version
                                       AND schedule.interval_seconds=segment.interval_seconds
                                       AND schedule.freshness_slo_seconds=
                                           segment.freshness_slo_seconds)
                                        AS schedule_active,
                                      (readiness.id=segment.eventization_readiness_id
                                       AND readiness.source_id=segment.source_id
                                       AND readiness.policy_version_id=
                                           segment.policy_version_id
                                       AND readiness.connector_config_version_id=
                                           segment.connector_config_version_id
                                       AND readiness.trial_run_id=segment.trial_run_id
                                       AND readiness.production_decision_id=
                                           segment.production_decision_id
                                       AND readiness.status='PASSED')
                                        AS eventization_pipeline_ready,
                                      to_jsonb(readiness) AS eventization_readiness,
                                      assignment.scheme,assignment.cohort_key,
                                      assignment.assigned_by,
                                      'PRODUCTION' AS execution_domain
                                 FROM round17_pilot_window_source segment
                                 JOIN source s ON s.id=segment.source_id
                                 LEFT JOIN source_policy_version p
                                   ON p.id=segment.policy_version_id
                                 LEFT JOIN connector_config_version config
                                   ON config.id=segment.connector_config_version_id
                                 LEFT JOIN source_trial_run trial ON trial.id=segment.trial_run_id
                                 LEFT JOIN source_trial_run_result result
                                   ON result.trial_run_id=trial.id
                                 LEFT JOIN source_governance_decision decision
                                   ON decision.id=segment.production_decision_id
                                 LEFT JOIN fetch_schedule schedule
                                   ON schedule.id=segment.schedule_id
                                 LEFT JOIN round17_eventization_readiness readiness
                                   ON readiness.id=segment.eventization_readiness_id
                                 LEFT JOIN source_governance_scheme_assignment assignment
                                   ON assignment.source_id=s.id
                                WHERE segment.window_id=:window
                                  AND segment.segment_number=1
                                ORDER BY segment.source_code
                                FOR UPDATE OF s"""
                        ),
                        {"window": window_id},
                    )
                )
                .mappings()
                .all()
            )
            schedule_ids = tuple(row["pinned_schedule_id"] for row in source_rows)
            current_database_revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            actor_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT actor_id,display_name,responsibility,local_identity
                                 FROM round17_staff_binding
                                WHERE display_name IN ('LEO','yinzi','baixuejiao')"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            actor_ids = {row["actor_id"] for row in actor_rows if not row["local_identity"]}
            local_count = sum(1 for row in actor_rows if row["local_identity"])
            bound_duties = {
                (row["display_name"], row["responsibility"])
                for row in actor_rows
                if not row["local_identity"]
            }
            required_duties = {
                ("LEO", "SOURCE_APPROVER"),
                ("LEO", "GOLD_ARBITRATOR"),
                ("yinzi", "SOURCE_OPERATOR"),
                ("yinzi", "SAFETY_ANNOTATOR_A"),
                ("yinzi", "DIGITAL_SECONDARY"),
                ("baixuejiao", "SAFETY_ANNOTATOR_B"),
                ("baixuejiao", "DIGITAL_PRIMARY"),
            }
            leo_ids = {
                row["actor_id"]
                for row in actor_rows
                if row["display_name"] == "LEO"
                and row["responsibility"] in {"SOURCE_APPROVER", "GOLD_ARBITRATOR"}
            }
            blockers: set[str] = set()
            if len(schedule_ids) != 20 or len(locked_schedule_ids) != 20:
                blockers.add("SOURCE_SCHEDULE_NOT_ACTIVE")
            blockers.update(
                _round17_snapshot_blockers(
                    window,
                    observed_source_codes=tuple(
                        str(row["source_code"]) for row in source_rows
                    ),
                    current_database_revision=(
                        str(current_database_revision)
                        if current_database_revision is not None
                        else None
                    ),
                    baseline_commit_attestation=(
                        self._round17_baseline_commit_attestation
                    ),
                    config_version_attestation=self._round17_config_version_attestation,
                    authoritative_source_codes=self._round17_roster_source_codes,
                )
            )
            observed_schedules: dict[str, _Round17ScheduleValues] = {
                str(row["source_code"]): (
                    int(row["current_interval_seconds"])
                    if row["current_interval_seconds"] is not None
                    else None,
                    int(row["current_freshness_slo_seconds"])
                    if row["current_freshness_slo_seconds"] is not None
                    else None,
                )
                for row in source_rows
            }
            authoritative_source_schedules = {
                str(row["source_code"]): _round17_schedule_values_from_authority(
                    row["poll_interval_minutes"], row["policy_document"]
                )
                for row in source_rows
            }
            blockers.update(
                _round17_schedule_attestation_blockers(
                    observed_schedules,
                    self._round17_source_schedule_attestations,
                    authoritative_source_schedules=authoritative_source_schedules,
                )
            )
            if actor_id not in leo_ids:
                blockers.add("WINDOW_STARTER_NOT_BOUND_APPROVER")
            if not required_duties.issubset(bound_duties):
                blockers.add("ROUND17_DUTY_BINDINGS_INCOMPLETE")
            for source in source_rows:
                if (
                    source["scheme"] != "R17_TWO_PERSON_MAKER_CHECKER_V1"
                    or source["cohort_key"] != window["roster_version"]
                    or source["assigned_by"] != actor_id
                ):
                    blockers.add("SOURCE_GOVERNANCE_SCHEME_MISMATCH")
            release = (
                (
                    await connection.execute(
                        text(
                            """SELECT sample_counts,agreement_metrics,frozen_by,source_codes,
                                      roster_version,gold_definition_version
                                 FROM round17_gold_release
                                WHERE version=:version AND status='FROZEN'"""
                        ),
                        {"version": window["gold_definition_version"]},
                    )
                )
                .mappings()
                .one_or_none()
            )
            release_counts = release["sample_counts"] if release is not None else {}
            release_agreement = release["agreement_metrics"] if release is not None else {}
            window_source_codes = tuple(str(row["source_code"]) for row in source_rows)
            release_source_codes = (
                tuple(str(code) for code in release["source_codes"])
                if release is not None
                else ()
            )
            gold_sources_match_window = _gold_release_sources_match_window(
                release_source_codes, window_source_codes
            )
            if release is not None and not gold_sources_match_window:
                blockers.add("GOLD_SOURCE_ROSTER_MISMATCH")
            release_frozen = bool(
                release is not None
                and release["frozen_by"] == actor_id
                and release["roster_version"] == window["roster_version"]
                and release["gold_definition_version"] == window["gold_definition_version"]
                and gold_sources_match_window
                and all(
                    int(release_counts.get(kind, 0)) >= required
                    for kind, required in _GOLD_REQUIRED_COUNTS.items()
                )
                and int(release_agreement.get("critical_safety_count", 0)) >= 20
                and float(release_agreement.get("raw_agreement", 0)) >= 0.95
                and release_agreement.get("coefficient_name") == "GWET_AC1"
                and float(release_agreement.get("coefficient", 0)) >= 0.80
                and int(release_agreement.get("digital_sample_count", 0)) > 0
                and int(release_agreement.get("digital_secondary_review_count", 0))
                >= ceil(int(release_agreement.get("digital_sample_count", 0)) * 0.20)
            )
            facts = PilotReadinessFacts(
                sources=tuple(
                    PilotSourceReadiness(
                        source_code=row["source_code"],
                        lifecycle_state=row["lifecycle_state"],
                        policy_approved=row["policy_status"] == "APPROVED",
                        approval_valid_until=row["approval_valid_until"],
                        connector_current=bool(row["connector_current"]),
                        live_trial_succeeded=bool(row["live_trial_succeeded"]),
                        production_approval_current=bool(row["production_approval_current"]),
                        schedule_active=bool(row["schedule_active"]),
                        eventization_pipeline_ready=bool(
                            row["eventization_pipeline_ready"]
                        )
                        and isinstance(row["eventization_readiness"], dict)
                        and _eventization_manifest_is_trusted(
                            row["eventization_readiness"],
                            source_code=str(row["source_code"]),
                            leo_actor_id=self._round17_leo_approver_actor_id,
                            trusted_public_key_base64=(
                                self._round17_eventization_trusted_public_key_base64
                            ),
                            trusted_public_key_sha256=(
                                self._round17_eventization_trusted_public_key_sha256
                            ),
                        ),
                        execution_domain=row["execution_domain"],
                    )
                    for row in source_rows
                ),
                controlled_oidc_actor_count=len(actor_ids),
                local_identity_count=local_count,
                gold_release_frozen=release_frozen,
                metric_definition_frozen=(
                    window["metric_definition_version"]
                    == _ROUND17_METRIC_DEFINITION_VERSION
                ),
                ai_enabled=self._ai_enabled,
                semantic_search_enabled=self._semantic_search_enabled,
                external_notifications_enabled=self._external_notifications_enabled,
            )
            readiness = evaluate_window_readiness(
                facts, starts_at=now, duration_hours=window["duration_hours"]
            )
            blockers.update(readiness.blocker_codes)
            if self._environment != "preproduction":
                blockers.add("ENVIRONMENT_NOT_PREPRODUCTION")
            if blockers:
                await connection.execute(
                    text(
                        """UPDATE round17_pilot_window
                              SET state='BLOCKED',version=version+1,blocker_codes=:blockers
                            WHERE id=:id"""
                    ),
                    {"id": window_id, "blockers": sorted(blockers)},
                )
            else:
                schedule_alignment = await connection.execute(
                    text(
                        """UPDATE fetch_schedule
                              SET next_run_at=:started,updated_at=:started
                            WHERE id=ANY(CAST(:ids AS uuid[])) AND status='ACTIVE'"""
                    ),
                    {"ids": list(schedule_ids), "started": now},
                )
                if schedule_alignment.rowcount != 20:
                    raise OperationsRejected(
                        "authoritative schedules could not be aligned atomically to T0"
                    )
                await connection.execute(
                    text(
                        """UPDATE round17_pilot_window
                              SET state='RUNNING',version=version+1,blocker_codes='{}'::text[],
                                  started_by=:actor,started_at=:started,ends_at=:ends
                            WHERE id=:id"""
                    ),
                    {
                        "id": window_id,
                        "actor": actor_id,
                        "started": now,
                        "ends": readiness.ends_at,
                    },
                )
                await connection.execute(
                    text(
                        """UPDATE round17_pilot_window_source
                              SET status='RUNNING',segment_started_at=:started,
                                  segment_ends_at=:ends
                            WHERE window_id=:window AND segment_number=1"""
                    ),
                    {"window": window_id, "started": now, "ends": readiness.ends_at},
                )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_WINDOW_START_EVALUATED',:actor,"
                    "'ROUND17_PILOT_WINDOW',:window,NULL,"
                    "jsonb_build_object('outcome',:outcome,'blocker_codes',"
                    "CAST(:blockers AS text[])),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "window": window_id,
                    "outcome": "BLOCKED" if blockers else "RUNNING",
                    "blockers": sorted(blockers),
                    "reason": payload.reason,
                    "request_id": idempotency_key,
                    "now": now,
                },
            )
            current_window = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source
                                        WHERE window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row WHERE id=:id"""
                        ),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one()
            )
        return _pilot_window_view(current_window)

    async def resume_pilot_source(
        self,
        window_id: UUID,
        source_code: str,
        payload: PilotSourceResumeRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        """Create a new immutable source segment from current authoritative facts."""

        self._require_round17_leo_actor(actor_id)
        now = self._now()
        async with self._engine.begin() as connection:
            prior_request = (
                (
                    await connection.execute(
                        text(
                            """SELECT segment.window_id,segment.source_code,window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source cohort
                                        WHERE cohort.window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window_source segment
                                 JOIN round17_pilot_window window_row
                                   ON window_row.id=segment.window_id
                                WHERE segment.resume_request_id=:request_id"""
                        ),
                        {"request_id": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if prior_request is not None:
                if (
                    prior_request["window_id"] != window_id
                    or prior_request["source_code"] != source_code
                ):
                    raise OperationsRejected(
                        "idempotency key is already bound to another source resume"
                    )
                return _pilot_window_view(prior_request)

            window = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_pilot_window WHERE id=:id FOR UPDATE"),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if window is None or window["state"] != "RUNNING":
                raise OperationsRejected("only a running pilot window can resume a source")
            if window["version"] != payload.expected_version:
                raise OperationsRejected("pilot window version conflict")
            if now < window["started_at"] or now >= window["ends_at"]:
                raise OperationsRejected("pilot source cannot resume outside its window")

            observed_source_codes = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT source_code "
                            "FROM round17_pilot_window_source WHERE window_id=:window"
                        ),
                        {"window": window_id},
                    )
                ).scalars()
            )
            current_database_revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            blockers = _round17_snapshot_blockers(
                window,
                observed_source_codes=observed_source_codes,
                current_database_revision=str(current_database_revision),
                baseline_commit_attestation=self._round17_baseline_commit_attestation,
                config_version_attestation=self._round17_config_version_attestation,
                authoritative_source_codes=self._round17_roster_source_codes,
            )
            if self._environment != "preproduction":
                blockers.add("ENVIRONMENT_NOT_PREPRODUCTION")
            if blockers:
                raise OperationsRejected(
                    "pilot source resume attestation failed: "
                    + ", ".join(sorted(blockers))
                )

            previous = (
                (
                    await connection.execute(
                        text(
                            """SELECT * FROM round17_pilot_window_source
                                WHERE window_id=:window AND source_code=:source_code
                                ORDER BY segment_number DESC LIMIT 1 FOR UPDATE"""
                        ),
                        {"window": window_id, "source_code": source_code},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if previous is None or previous["status"] != "PAUSED":
                raise OperationsRejected("the latest source segment is not paused")
            if previous["pause_reason"] not in {
                "SOURCE_AUTHORITY_CHANGED",
                "SOURCE_SCHEDULE_CHANGED",
                "SOURCE_RUNTIME_ANOMALY",
            }:
                raise OperationsRejected("the source pause has no approved recovery gate")

            authority = (
                (
                    await connection.execute(
                        text(
                            """SELECT source_row.id AS source_id,
                                      source_row.current_policy_version_id AS policy_id,
                                      source_row.current_connector_config_version_id AS config_id,
                                      schedule.id AS schedule_id,
                                      schedule.version AS schedule_version,
                                      schedule.interval_seconds,
                                      schedule.freshness_slo_seconds,
                                      source_row.current_trial_run_id AS trial_id,
                                      decision.id AS production_decision_id,
                                      readiness.id AS eventization_readiness_id,
                                      to_jsonb(readiness) AS eventization_readiness
                                 FROM source source_row
                                 JOIN source_policy_version policy
                                   ON policy.id=source_row.current_policy_version_id
                                  AND policy.source_id=source_row.id
                                 JOIN connector_config_version config
                                   ON config.id=
                                      source_row.current_connector_config_version_id
                                  AND config.source_id=source_row.id
                                  AND config.policy_version_id=policy.id
                                 JOIN fetch_schedule schedule
                                   ON schedule.source_id=source_row.id
                                 JOIN source_trial_run trial
                                   ON trial.id=source_row.current_trial_run_id
                                  AND trial.source_id=source_row.id
                                 JOIN source_trial_run_result result
                                   ON result.trial_run_id=trial.id
                                 JOIN LATERAL (
                                   SELECT production.*
                                     FROM source_governance_decision production
                                    WHERE production.source_id=source_row.id
                                      AND production.decision_type='PRODUCTION_APPROVAL'
                                    ORDER BY production.created_at DESC,production.id DESC
                                    LIMIT 1
                                 ) decision ON true
                                 JOIN source_governance_scheme_assignment assignment
                                   ON assignment.source_id=source_row.id
                                 JOIN round17_staff_binding leo
                                   ON leo.actor_id=:actor
                                  AND leo.display_name='LEO'
                                  AND leo.responsibility='SOURCE_APPROVER'
                                  AND leo.local_identity=false
                                 JOIN round17_eventization_readiness readiness
                                   ON readiness.source_id=source_row.id
                                  AND readiness.policy_version_id=policy.id
                                  AND readiness.connector_config_version_id=config.id
                                  AND readiness.trial_run_id=trial.id
                                  AND readiness.production_decision_id=decision.id
                                  AND readiness.status='PASSED'
                                WHERE source_row.id=:source
                                  AND source_row.registry_code=:source_code
                                  AND source_row.lifecycle_state='ACTIVE'
                                  AND policy.status='APPROVED'
                                  AND policy.valid_from<=:now
                                  AND policy.valid_until>=:ends
                                  AND policy.document->>'storage_policy'=
                                      'RAW_EVIDENCE_ALLOWED'
                                  AND config.validation_status='VALID'
                                  AND schedule.status='ACTIVE'
                                  AND trial.kind='LIVE_TRIAL'
                                  AND trial.execution_domain='TRIAL'
                                  AND trial.policy_version_id=policy.id
                                  AND trial.connector_config_version_id=config.id
                                  AND result.status='SUCCEEDED'
                                  AND decision.outcome='APPROVED'
                                  AND decision.policy_version_id=policy.id
                                  AND decision.connector_config_version_id=config.id
                                  AND decision.trial_run_id=trial.id
                                  AND decision.decided_by=:actor
                                  AND (decision.valid_until IS NULL
                                       OR decision.valid_until>=:ends)
                                  AND assignment.scheme=
                                      'R17_TWO_PERSON_MAKER_CHECKER_V1'
                                  AND assignment.cohort_key=:roster
                                  AND assignment.assigned_by=:actor
                                  AND source_v2_policy_compliance_approved(
                                        source_row.id,policy.id,:now
                                      ) IS TRUE
                                  AND (
                                    :pause_reason<>'SOURCE_RUNTIME_ANOMALY'
                                    OR NOT EXISTS (
                                      SELECT 1 FROM source_anomaly anomaly
                                       WHERE anomaly.source_id=source_row.id
                                         AND (
                                           anomaly.severity='CRITICAL'
                                           OR anomaly.code IN (
                                             'ZERO_DISCOVERY_STREAK',
                                             'BODY_LENGTH_SHIFT',
                                             'REQUIRED_FIELDS_MISSING',
                                             'DOM_FINGERPRINT_CHANGED'
                                           )
                                         )
                                         AND (
                                           anomaly.status<>'RESOLVED'
                                           OR anomaly.resolved_at IS NULL
                                         )
                                    )
                                  )
                                FOR UPDATE OF source_row,policy,config,schedule,
                                  trial,assignment,readiness"""
                        ),
                        {
                            "actor": actor_id,
                            "source": previous["source_id"],
                            "source_code": source_code,
                            "now": now,
                            "ends": window["ends_at"],
                            "roster": window["roster_version"],
                            "pause_reason": previous["pause_reason"],
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if authority is None:
                raise OperationsRejected(
                    "current source authority is not eligible for resume"
                )
            authority_readiness = authority["eventization_readiness"]
            if not isinstance(
                authority_readiness, dict
            ) or not _eventization_manifest_is_trusted(
                authority_readiness,
                source_code=source_code,
                leo_actor_id=self._round17_leo_approver_actor_id,
                trusted_public_key_base64=(
                    self._round17_eventization_trusted_public_key_base64
                ),
                trusted_public_key_sha256=(
                    self._round17_eventization_trusted_public_key_sha256
                ),
            ):
                raise OperationsRejected(
                    "current eventization readiness signature is not trusted"
                )

            segment_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO round17_pilot_window_source (
                         id,window_id,source_id,source_code,policy_version_id,
                         connector_config_version_id,schedule_id,schedule_version,
                         interval_seconds,freshness_slo_seconds,trial_run_id,
                         production_decision_id,eventization_readiness_id,
                         segment_number,status,segment_started_at,segment_ends_at,
                         resumed_by,resume_reason,resume_request_id,created_at
                       ) VALUES (
                         :id,:window,:source,:source_code,:policy,:config,:schedule,
                         :schedule_version,:interval,:slo,:trial,:decision,:readiness,
                         :segment_number,'RUNNING',:now,:ends,:actor,:reason,:request_id,:now
                       )"""
                ),
                {
                    "id": segment_id,
                    "window": window_id,
                    "source": authority["source_id"],
                    "source_code": source_code,
                    "policy": authority["policy_id"],
                    "config": authority["config_id"],
                    "schedule": authority["schedule_id"],
                    "schedule_version": authority["schedule_version"],
                    "interval": authority["interval_seconds"],
                    "slo": authority["freshness_slo_seconds"],
                    "trial": authority["trial_id"],
                    "decision": authority["production_decision_id"],
                    "readiness": authority["eventization_readiness_id"],
                    "segment_number": int(previous["segment_number"]) + 1,
                    "now": now,
                    "ends": window["ends_at"],
                    "actor": actor_id,
                    "reason": payload.reason,
                    "request_id": idempotency_key,
                },
            )
            new_version = await connection.scalar(
                text("SELECT version FROM round17_pilot_window WHERE id=:id"),
                {"id": window_id},
            )
            if int(new_version or 0) != int(window["version"]) + 1:
                raise OperationsRejected("source resume did not version the pilot window")
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_SOURCE_RESUMED',:actor,"
                    "'ROUND17_PILOT_WINDOW_SOURCE',:segment,NULL,"
                    "jsonb_build_object('window_id',:window,'source_code',:source_code,"
                    "'segment_number',:segment_number),:reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "segment": segment_id,
                    "window": window_id,
                    "source_code": source_code,
                    "segment_number": int(previous["segment_number"]) + 1,
                    "reason": payload.reason,
                    "request_id": idempotency_key,
                    "now": now,
                },
            )
            current_window = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source
                                        WHERE window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row WHERE id=:id"""
                        ),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one()
            )
        return _pilot_window_view(current_window)

    async def complete_pilot_window(
        self,
        window_id: UUID,
        payload: PilotWindowCompleteRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> PilotWindowView:
        """Finalize an elapsed window while preserving paused and failed source facts."""

        self._require_round17_leo_actor(actor_id)
        now = self._now()
        async with self._engine.begin() as connection:
            window = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_pilot_window WHERE id=:id FOR UPDATE"),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if window is None or window["state"] != "RUNNING":
                raise OperationsRejected("only a running pilot window can be completed")
            if window["version"] != payload.expected_version:
                raise OperationsRejected("pilot window version conflict")
            if now < window["ends_at"]:
                raise OperationsRejected("pilot window cannot complete before ends_at")

            leo_bound = await connection.scalar(
                text(
                    """SELECT 1 FROM round17_staff_binding
                        WHERE actor_id=:actor AND display_name='LEO'
                          AND responsibility='SOURCE_APPROVER'
                          AND local_identity=false"""
                ),
                {"actor": actor_id},
            )
            if not leo_bound:
                raise OperationsRejected("pilot completion requires the bound LEO approver")

            observed_source_codes = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT source_code "
                            "FROM round17_pilot_window_source WHERE window_id=:window"
                        ),
                        {"window": window_id},
                    )
                ).scalars()
            )
            current_database_revision = await connection.scalar(
                text("SELECT version_num FROM alembic_version")
            )
            blockers = _round17_snapshot_blockers(
                window,
                observed_source_codes=observed_source_codes,
                current_database_revision=str(current_database_revision),
                baseline_commit_attestation=self._round17_baseline_commit_attestation,
                config_version_attestation=self._round17_config_version_attestation,
                authoritative_source_codes=self._round17_roster_source_codes,
            )
            if self._environment != "preproduction":
                blockers.add("ENVIRONMENT_NOT_PREPRODUCTION")
            if blockers:
                raise OperationsRejected(
                    "pilot completion attestation failed: "
                    + ", ".join(sorted(blockers))
                )

            await connection.execute(
                text(
                    "SELECT id FROM round17_pilot_window_source "
                    "WHERE window_id=:window FOR UPDATE"
                ),
                {"window": window_id},
            )
            latest = (
                (
                    await connection.execute(
                        text(
                            """SELECT DISTINCT ON (source_id)
                                      source_id,source_code,status,segment_number
                                 FROM round17_pilot_window_source
                                WHERE window_id=:window
                                ORDER BY source_id,segment_number DESC"""
                        ),
                        {"window": window_id},
                    )
                )
                .mappings()
                .all()
            )
            if (
                len(latest) != 20
                or len({row["source_code"] for row in latest}) != 20
                or any(
                    row["status"]
                    not in {"RUNNING", "PAUSED", "COMPLETED", "FAILED"}
                    for row in latest
                )
            ):
                raise OperationsRejected(
                    "pilot window requires 20 honest final source states"
                )
            await connection.execute(
                text(
                    """UPDATE round17_pilot_window_source
                          SET status='COMPLETED'
                        WHERE window_id=:window AND status='RUNNING'
                          AND segment_ends_at<=:now"""
                ),
                {"window": window_id, "now": now},
            )
            await connection.execute(
                text(
                    """UPDATE round17_pilot_window
                          SET state='COMPLETED',version=version+1
                        WHERE id=:window"""
                ),
                {"window": window_id},
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_WINDOW_COMPLETED',:actor,"
                    "'ROUND17_PILOT_WINDOW',:window,NULL,"
                    "jsonb_build_object('source_count',20,'completed_at',:now),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "window": window_id,
                    "now": now,
                    "reason": payload.reason,
                    "request_id": idempotency_key,
                },
            )
            current_window = (
                (
                    await connection.execute(
                        text(
                            """SELECT window_row.*,
                                      (SELECT count(DISTINCT source_id)
                                         FROM round17_pilot_window_source
                                        WHERE window_id=window_row.id) AS source_count
                                 FROM round17_pilot_window window_row WHERE id=:id"""
                        ),
                        {"id": window_id},
                    )
                )
                .mappings()
                .one()
            )
        return _pilot_window_view(current_window)

    async def list_gold_tasks(self, *, actor_id: UUID) -> list[GoldTaskView]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT DISTINCT task.id,task.sample_kind,task.sample_ref,
                                      task.source_code,task.domain,
                                      task.production_decision_id,task.critical_safety,
                                      task.secondary_review_required,task.status,task.assigned_at
                                 FROM round17_gold_task task
                                 LEFT JOIN round17_gold_assignment assignment
                                   ON assignment.task_id=task.id
                                WHERE assignment.annotator_id=:actor
                                   OR (task.status='DISAGREEMENT' AND EXISTS (
                                     SELECT 1 FROM round17_staff_binding binding
                                      WHERE binding.actor_id=:actor
                                        AND binding.responsibility='GOLD_ARBITRATOR'
                                   ))
                                ORDER BY task.assigned_at,task.id"""
                        ),
                        {"actor": actor_id},
                    )
                )
                .mappings()
                .all()
            )
        return [_gold_task_view(row) for row in rows]

    async def create_gold_task(
        self, payload: GoldTaskCreateRequest, *, actor_id: UUID
    ) -> GoldTaskView:
        now = self._now()
        self._require_round17_leo_actor(actor_id)
        task_id = uuid7()
        sample_ref_hash = sha256(payload.sample_ref.encode("utf-8")).hexdigest()
        async with self._engine.begin() as connection:
            is_arbitrator = await connection.scalar(
                text(
                    "SELECT 1 FROM round17_staff_binding WHERE actor_id=:actor "
                    "AND responsibility='GOLD_ARBITRATOR' AND local_identity=false"
                ),
                {"actor": actor_id},
            )
            source = (
                (
                    await connection.execute(
                        text(
                            """SELECT s.id,s.registry_code,s.content_domains
                                 FROM source s
                                 JOIN source_policy_version policy
                                   ON policy.id=s.current_policy_version_id
                                 JOIN connector_config_version config
                                   ON config.id=s.current_connector_config_version_id
                                 JOIN source_trial_run trial ON trial.id=s.current_trial_run_id
                                 JOIN source_trial_run_result result
                                   ON result.trial_run_id=trial.id
                                 JOIN source_governance_decision decision
                                   ON decision.id=:decision
                                  AND decision.source_id=s.id
                                  AND decision.policy_version_id=policy.id
                                  AND decision.connector_config_version_id=config.id
                                  AND decision.trial_run_id=trial.id
                                 JOIN source_governance_scheme_assignment assignment
                                   ON assignment.source_id=s.id
                                WHERE s.registry_code=:source_code
                                  AND s.lifecycle_state='ACTIVE'
                                  AND policy.status='APPROVED'
                                  AND policy.valid_from<=:now AND policy.valid_until>:now
                                  AND config.validation_status='VALID'
                                  AND trial.kind='LIVE_TRIAL'
                                  AND trial.execution_domain='TRIAL'
                                  AND result.status='SUCCEEDED'
                                  AND decision.decision_type='PRODUCTION_APPROVAL'
                                  AND decision.outcome='APPROVED'
                                  AND (decision.valid_until IS NULL OR decision.valid_until>:now)
                                  AND assignment.scheme='R17_TWO_PERSON_MAKER_CHECKER_V1'
                                  AND assignment.cohort_key=:roster_version"""
                        ),
                        {
                            "decision": payload.production_decision_id,
                            "source_code": payload.source_code,
                            "roster_version": _ROUND17_ROSTER_VERSION,
                            "now": now,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            annotator_bindings = (
                (
                    await connection.execute(
                        text(
                            """SELECT actor_id,display_name,responsibility
                                 FROM round17_staff_binding
                                WHERE actor_id=ANY(CAST(:actors AS uuid[]))
                                  AND responsibility IN (
                                    'SAFETY_ANNOTATOR_A','SAFETY_ANNOTATOR_B',
                                    'DIGITAL_PRIMARY','DIGITAL_SECONDARY'
                                  ) AND local_identity=false"""
                        ),
                        {"actors": payload.assigned_annotator_ids},
                    )
                )
                .mappings()
                .all()
            )
            bound_actor_ids = {row["actor_id"] for row in annotator_bindings}
            if (
                not is_arbitrator
                or source is None
                or bound_actor_ids != set(payload.assigned_annotator_ids)
            ):
                raise OperationsRejected("gold duties are not bound to controlled OIDC identities")
            if actor_id in payload.assigned_annotator_ids:
                raise OperationsRejected("gold arbitrator cannot annotate the same task")
            if not _source_supports_gold_domain(
                tuple(str(value) for value in source["content_domains"]),
                payload.domain.value,
            ):
                raise OperationsRejected(
                    "gold domain is not authorized by the source content domains"
                )
            sample_identities = tuple(
                UUID(value) for value in payload.sample_ref.split(":")[3:]
            )
            if payload.sample_kind is GoldSampleKind.SEARCH_QUESTION:
                raise OperationsRejected(
                    "search-question gold is blocked until an approved authority entity exists"
                )
            if not await _gold_sample_is_authoritative(
                connection,
                sample_kind=payload.sample_kind,
                identities=sample_identities,
                source_id=source["id"],
            ):
                raise OperationsRejected(
                    "gold sample is not an authoritative production source fact"
                )
            if payload.critical_safety:
                critical_duties = {
                    (row["display_name"], row["responsibility"])
                    for row in annotator_bindings
                    if row["responsibility"]
                    in {"SAFETY_ANNOTATOR_A", "SAFETY_ANNOTATOR_B"}
                }
                if critical_duties != {
                    ("yinzi", "SAFETY_ANNOTATOR_A"),
                    ("baixuejiao", "SAFETY_ANNOTATOR_B"),
                }:
                    raise OperationsRejected(
                        "critical safety gold requires yinzi and baixuejiao blind labels"
                    )
            if payload.domain.value == "DIGITAL":
                digital_duties = {
                    (row["display_name"], row["responsibility"])
                    for row in annotator_bindings
                    if row["responsibility"] in {"DIGITAL_PRIMARY", "DIGITAL_SECONDARY"}
                }
                required_digital_duties = {("baixuejiao", "DIGITAL_PRIMARY")}
                if payload.secondary_review_required:
                    required_digital_duties.add(("yinzi", "DIGITAL_SECONDARY"))
                if digital_duties != required_digital_duties:
                    raise OperationsRejected(
                        "digital gold requires baixuejiao primary and yinzi secondary review"
                    )
            await connection.execute(
                text(
                    """INSERT INTO round17_gold_task (
                         id,source_id,source_code,domain,roster_version,
                         gold_definition_version,production_decision_id,
                         sample_kind,sample_ref,sample_ref_sha256,critical_safety,
                         secondary_review_required,blinding_key_sha256,status,
                         created_by,assigned_at
                       ) VALUES (
                         :id,:source,:source_code,:domain,:roster_version,:gold_version,
                         :decision,:kind,:ref,:ref_hash,
                         :critical,:secondary,:blind,'ASSIGNED',:actor,:now
                       )"""
                ),
                {
                    "id": task_id,
                    "source": source["id"],
                    "source_code": payload.source_code,
                    "domain": payload.domain.value,
                    "roster_version": _ROUND17_ROSTER_VERSION,
                    "gold_version": _ROUND17_GOLD_DEFINITION_VERSION,
                    "decision": payload.production_decision_id,
                    "kind": payload.sample_kind.value,
                    "ref": payload.sample_ref,
                    "ref_hash": sample_ref_hash,
                    "critical": payload.critical_safety,
                    "secondary": payload.secondary_review_required,
                    "blind": sha256(f"{task_id}:{sample_ref_hash}".encode()).hexdigest(),
                    "actor": actor_id,
                    "now": now,
                },
            )
            for annotator_id in payload.assigned_annotator_ids:
                await connection.execute(
                    text(
                        """INSERT INTO round17_gold_assignment
                           (id,task_id,annotator_id,assigned_at)
                           VALUES (:id,:task,:annotator,:now)"""
                    ),
                    {"id": uuid7(), "task": task_id, "annotator": annotator_id, "now": now},
                )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_GOLD_TASK_ASSIGNED',:actor,"
                    "'ROUND17_GOLD_TASK',:task,NULL,jsonb_build_object('sample_kind',:kind),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "task": task_id,
                    "kind": payload.sample_kind.value,
                    "reason": payload.reason,
                    "request_id": f"round17-gold-task:{task_id}",
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_gold_task WHERE id=:id"), {"id": task_id}
                    )
                )
                .mappings()
                .one()
            )
        return _gold_task_view(row)

    async def submit_gold_annotation(
        self, payload: GoldAnnotationRequest, *, actor_id: UUID
    ) -> GoldAnnotationView:
        now = self._now()
        annotation_id = uuid7()
        async with self._engine.begin() as connection:
            task = (
                (
                    await connection.execute(
                        text(
                            """SELECT task.* FROM round17_gold_task task
                                 JOIN round17_gold_assignment assignment
                                   ON assignment.task_id=task.id
                                WHERE task.id=:task AND assignment.annotator_id=:actor
                                  AND task.status NOT IN ('ARBITRATED','FROZEN')
                                FOR UPDATE OF task"""
                        ),
                        {"task": payload.task_id, "actor": actor_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if task is None or task["sample_kind"] != payload.sample_kind.value:
                raise OperationsRejected("gold task is not assigned to this annotator")
            if not await _gold_annotation_evidence_is_authoritative(
                connection,
                evidence_ids=payload.evidence_ids,
                source_id=task["source_id"],
                sample_kind=payload.sample_kind,
                sample_ref=task["sample_ref"],
            ):
                raise OperationsRejected(
                    "gold annotation evidence is not an accepted production source fact"
                )
            await connection.execute(
                text(
                    """INSERT INTO round17_gold_annotation (
                         id,task_id,annotator_id,sample_kind,decision_code,label_value,
                         evidence_ids,related_sample_refs,status,submitted_at
                       ) VALUES (
                         :id,:task,:actor,:kind,:decision,:label,:evidence,:related,
                         'SUBMITTED',:now
                       )"""
                ),
                {
                    "id": annotation_id,
                    "task": payload.task_id,
                    "actor": actor_id,
                    "kind": payload.sample_kind.value,
                    "decision": payload.decision_code,
                    "label": payload.label_value,
                    "evidence": payload.evidence_ids,
                    "related": payload.related_sample_refs,
                    "now": now,
                },
            )
            assignment_count = int(
                await connection.scalar(
                    text("SELECT count(*) FROM round17_gold_assignment WHERE task_id=:task"),
                    {"task": payload.task_id},
                )
                or 0
            )
            annotations = (
                (
                    await connection.execute(
                        text(
                            """SELECT id,decision_code,label_value,evidence_ids,
                                      related_sample_refs
                                 FROM round17_gold_annotation
                                WHERE task_id=:task AND status='SUBMITTED'
                                ORDER BY id"""
                        ),
                        {"task": payload.task_id},
                    )
                )
                .mappings()
                .all()
            )
            if len(annotations) == assignment_count:
                signatures = {
                    _gold_manifest_sha256(
                        [
                            {
                                "decision_code": row["decision_code"],
                                "label_value": row["label_value"],
                                "evidence_ids": row["evidence_ids"],
                                "related_sample_refs": row["related_sample_refs"],
                            }
                        ]
                    )
                    for row in annotations
                }
                status_value = "SUBMITTED" if len(signatures) == 1 else "DISAGREEMENT"
                await connection.execute(
                    text("UPDATE round17_gold_task SET status=:status WHERE id=:task"),
                    {"status": status_value, "task": payload.task_id},
                )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_gold_annotation WHERE id=:id"),
                        {"id": annotation_id},
                    )
                )
                .mappings()
                .one()
            )
        return _gold_annotation_view(row)

    async def arbitrate_gold_task(
        self, payload: GoldArbitrationRequest, *, actor_id: UUID
    ) -> GoldTaskView:
        self._require_round17_leo_actor(actor_id)
        now = self._now()
        async with self._engine.begin() as connection:
            eligible = await connection.scalar(
                text(
                    """SELECT 1 FROM round17_gold_task task
                        JOIN round17_gold_annotation annotation
                          ON annotation.task_id=task.id
                        WHERE task.id=:task AND task.status='DISAGREEMENT'
                          AND annotation.id=:annotation
                          AND NOT EXISTS (
                            SELECT 1 FROM round17_gold_assignment assignment
                             WHERE assignment.task_id=task.id
                               AND assignment.annotator_id=:actor
                          )
                          AND EXISTS (
                            SELECT 1 FROM round17_staff_binding binding
                             WHERE binding.actor_id=:actor
                               AND binding.responsibility='GOLD_ARBITRATOR'
                               AND binding.local_identity=false
                          )"""
                ),
                {
                    "task": payload.task_id,
                    "annotation": payload.selected_annotation_id,
                    "actor": actor_id,
                },
            )
            if not eligible:
                raise OperationsRejected("gold arbitration is not authorized")
            await connection.execute(
                text(
                    """INSERT INTO round17_gold_arbitration (
                         id,task_id,selected_annotation_id,arbitrator_id,reason,arbitrated_at
                       ) VALUES (:id,:task,:annotation,:actor,:reason,:now)"""
                ),
                {
                    "id": uuid7(),
                    "task": payload.task_id,
                    "annotation": payload.selected_annotation_id,
                    "actor": actor_id,
                    "reason": payload.reason,
                    "now": now,
                },
            )
            await connection.execute(
                text("UPDATE round17_gold_task SET status='ARBITRATED' WHERE id=:task"),
                {"task": payload.task_id},
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_gold_task WHERE id=:task"),
                        {"task": payload.task_id},
                    )
                )
                .mappings()
                .one()
            )
        return _gold_task_view(row)

    async def get_gold_arbitration_packet(
        self, task_id: UUID, *, actor_id: UUID
    ) -> GoldArbitrationPacket:
        self._require_round17_leo_actor(actor_id)
        async with self._engine.connect() as connection:
            task = (
                (
                    await connection.execute(
                        text(
                            """SELECT task.* FROM round17_gold_task task
                                WHERE task.id=:task AND task.status='DISAGREEMENT'
                                  AND NOT EXISTS (
                                    SELECT 1 FROM round17_gold_assignment assignment
                                     WHERE assignment.task_id=task.id
                                       AND assignment.annotator_id=:actor
                                  )
                                  AND EXISTS (
                                    SELECT 1 FROM round17_staff_binding binding
                                     WHERE binding.actor_id=:actor
                                       AND binding.responsibility='GOLD_ARBITRATOR'
                                       AND binding.local_identity=false
                                  )"""
                        ),
                        {"task": task_id, "actor": actor_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if task is None:
                raise OperationsRejected("gold arbitration packet is not authorized")
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT id AS annotation_id,decision_code,label_value,
                                      evidence_ids,related_sample_refs
                                 FROM round17_gold_annotation
                                WHERE task_id=:task AND status='SUBMITTED'
                                ORDER BY id"""
                        ),
                        {"task": task_id},
                    )
                )
                .mappings()
                .all()
            )
        return GoldArbitrationPacket(
            task=_gold_task_view(task),
            options=[GoldArbitrationOption.model_validate(row) for row in rows],
        )

    async def freeze_gold_release(
        self, payload: GoldReleaseRequest, *, actor_id: UUID
    ) -> GoldReleaseView:
        now = self._now()
        self._require_round17_leo_actor(actor_id)
        if payload.version != _ROUND17_GOLD_DEFINITION_VERSION:
            raise OperationsRejected("gold release version is not the approved Round 17 definition")
        authoritative_source_codes = tuple(
            sorted(self._round17_roster_source_codes or ())
        )
        if (
            len(authoritative_source_codes) != 20
            or len(set(authoritative_source_codes)) != 20
        ):
            raise OperationsRejected(
                "gold release requires the exact authoritative 20-source roster"
            )
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_gold_release WHERE version=:version"),
                        {"version": payload.version},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                if not _gold_release_sources_match_window(
                    tuple(str(code) for code in existing["source_codes"]),
                    authoritative_source_codes,
                ):
                    raise OperationsRejected(
                        "existing gold release does not match the authoritative roster"
                    )
                return GoldReleaseView.model_validate(existing)
            matching_window = await connection.scalar(
                text(
                    """SELECT EXISTS (
                         SELECT 1 FROM round17_pilot_window window_row
                          WHERE window_row.roster_version=:roster
                            AND window_row.gold_definition_version=:gold
                            AND (
                              SELECT array_agg(DISTINCT segment.source_code
                                               ORDER BY segment.source_code)
                                FROM round17_pilot_window_source segment
                               WHERE segment.window_id=window_row.id
                            )=CAST(:source_codes AS text[])
                       )"""
                ),
                {
                    "roster": _ROUND17_ROSTER_VERSION,
                    "gold": _ROUND17_GOLD_DEFINITION_VERSION,
                    "source_codes": list(authoritative_source_codes),
                },
            )
            if not matching_window:
                raise OperationsRejected(
                    "gold release roster has no matching authoritative pilot window"
                )
            is_arbitrator = await connection.scalar(
                text(
                    "SELECT 1 FROM round17_staff_binding WHERE actor_id=:actor "
                    "AND responsibility='GOLD_ARBITRATOR' AND local_identity=false"
                ),
                {"actor": actor_id},
            )
            if not is_arbitrator:
                raise OperationsRejected("gold release requires the bound arbitrator")
            tasks = (
                (
                    await connection.execute(
                        text(
                            """SELECT task.id,task.sample_kind,task.domain,task.source_code,
                                      task.roster_version,task.gold_definition_version,
                                      task.critical_safety,
                                      task.secondary_review_required,task.status,
                                      (SELECT count(*) FROM round17_gold_annotation annotation
                                        WHERE annotation.task_id=task.id
                                          AND annotation.status='SUBMITTED')
                                        AS annotation_count,
                                      (SELECT count(*) FROM round17_gold_assignment assignment
                                        WHERE assignment.task_id=task.id)
                                        AS assignment_count,
                                      arbitration.selected_annotation_id
                                 FROM round17_gold_task task
                                 LEFT JOIN round17_gold_arbitration arbitration
                                   ON arbitration.task_id=task.id
                                WHERE task.status<>'FROZEN'
                                ORDER BY task.id FOR UPDATE OF task"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            counts = {kind: 0 for kind in _GOLD_REQUIRED_COUNTS}
            task_ids: list[UUID] = []
            critical_safety_count = 0
            digital_count = 0
            digital_secondary_count = 0
            source_codes: set[str] = set()
            for task in tasks:
                if (
                    task["roster_version"] != _ROUND17_ROSTER_VERSION
                    or task["gold_definition_version"] != _ROUND17_GOLD_DEFINITION_VERSION
                ):
                    raise OperationsRejected("gold task version pins do not match the release")
                counts[str(task["sample_kind"])] += 1
                source_codes.add(str(task["source_code"]))
                task_ids.append(task["id"])
                annotation_count = int(task["annotation_count"])
                assignment_count = int(task["assignment_count"])
                if annotation_count != assignment_count:
                    raise OperationsRejected("gold release contains incomplete annotations")
                if task["critical_safety"] and annotation_count != 2:
                    raise OperationsRejected("critical safety gold requires two annotations")
                if task["critical_safety"]:
                    critical_safety_count += 1
                if task["domain"] == "DIGITAL":
                    digital_count += 1
                    if annotation_count == 2 and task["secondary_review_required"]:
                        digital_secondary_count += 1
                if task["status"] == "DISAGREEMENT" or task["status"] == "ASSIGNED":
                    raise OperationsRejected("gold release contains unresolved tasks")
                if task["status"] == "ARBITRATED" and task["selected_annotation_id"] is None:
                    raise OperationsRejected("gold arbitration evidence is incomplete")
            missing = {
                kind: required - counts.get(kind, 0)
                for kind, required in _GOLD_REQUIRED_COUNTS.items()
                if counts.get(kind, 0) < required
            }
            if missing:
                raise OperationsRejected(
                    "gold sample minimums are not met: "
                    + ", ".join(
                        f"{kind}={shortfall}" for kind, shortfall in sorted(missing.items())
                    )
                )
            if critical_safety_count < 20:
                raise OperationsRejected(
                    "gold release requires at least 20 critical safety double labels"
                )
            if digital_count == 0 or digital_secondary_count < ceil(digital_count * 0.20):
                raise OperationsRejected(
                    "gold release requires blind secondary review for 20 percent of digital tasks"
                )
            if not _gold_release_sources_match_window(
                tuple(sorted(source_codes)), authoritative_source_codes
            ):
                raise OperationsRejected(
                    "gold release tasks must cover the exact authoritative 20-source roster"
                )
            manifest_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT task.id AS task_id,task.sample_kind,task.domain,
                                      task.roster_version,task.gold_definition_version,
                                      task.source_code,task.production_decision_id,
                                      task.sample_ref_sha256,task.critical_safety,
                                      task.secondary_review_required,
                                      annotation.id AS annotation_id,
                                      annotation.annotator_id,annotation.decision_code,
                                      annotation.label_value,annotation.evidence_ids,
                                      annotation.related_sample_refs,
                                      arbitration.selected_annotation_id
                                 FROM round17_gold_task task
                                 JOIN round17_gold_annotation annotation
                                   ON annotation.task_id=task.id
                                 LEFT JOIN round17_gold_arbitration arbitration
                                   ON arbitration.task_id=task.id
                                WHERE task.id=ANY(CAST(:tasks AS uuid[]))
                                ORDER BY task.id,annotation.id"""
                        ),
                        {"tasks": task_ids},
                    )
                )
                .mappings()
                .all()
            )
            manifest_records = [dict(row) for row in manifest_rows]
            agreement_records = [
                {
                    "task_id": str(row["task_id"]),
                    "signature": _gold_manifest_sha256(
                        [
                            {
                                "decision_code": row["decision_code"],
                                "label_value": row["label_value"],
                            }
                        ]
                    ),
                }
                for row in manifest_rows
                if row["critical_safety"]
            ]
            agreement_metrics = _gold_agreement_metrics(agreement_records)
            if (
                float(agreement_metrics["raw_agreement"]) < 0.95
                or float(agreement_metrics["coefficient"]) < 0.80
            ):
                raise OperationsRejected(
                    "gold agreement is below raw 0.95 or Gwet AC1 0.80"
                )
            agreement_metrics.update(
                {
                    "critical_safety_count": critical_safety_count,
                    "digital_sample_count": digital_count,
                    "digital_secondary_review_count": digital_secondary_count,
                }
            )
            manifest_hash = _gold_manifest_sha256(manifest_records)
            release_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO round17_gold_release (
                         id,version,roster_version,gold_definition_version,source_codes,
                         manifest_sha256,sample_counts,agreement_metrics,frozen_by,
                         frozen_at,status
                       ) VALUES (
                         :id,:version,:roster_version,:gold_version,:source_codes,:manifest,
                         CAST(:counts AS jsonb),
                         CAST(:agreement AS jsonb),
                         :actor,:now,'FROZEN'
                       )"""
                ),
                {
                    "id": release_id,
                    "version": payload.version,
                    "roster_version": _ROUND17_ROSTER_VERSION,
                    "gold_version": _ROUND17_GOLD_DEFINITION_VERSION,
                    "source_codes": list(authoritative_source_codes),
                    "manifest": manifest_hash,
                    "counts": json.dumps(counts, sort_keys=True),
                    "agreement": json.dumps(agreement_metrics, sort_keys=True),
                    "actor": actor_id,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "UPDATE round17_gold_task SET status='FROZEN' "
                    "WHERE id=ANY(CAST(:tasks AS uuid[]))"
                ),
                {"tasks": task_ids},
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_GOLD_RELEASE_FROZEN',:actor,"
                    "'ROUND17_GOLD_RELEASE',:release,NULL,"
                    "jsonb_build_object('version',:version,'manifest_sha256',:manifest),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "release": release_id,
                    "version": payload.version,
                    "manifest": manifest_hash,
                    "reason": payload.reason,
                    "request_id": f"round17-gold-release:{payload.version}",
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_gold_release WHERE id=:id"),
                        {"id": release_id},
                    )
                )
                .mappings()
                .one()
            )
        return GoldReleaseView.model_validate(row)

    async def list_operator_tasks(self, *, actor_id: UUID) -> list[OperatorTaskView]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT * FROM round17_operator_task
                                WHERE assigned_to=:actor OR created_by=:actor
                                ORDER BY created_at,id"""
                        ),
                        {"actor": actor_id},
                    )
                )
                .mappings()
                .all()
            )
        return [_operator_task_view(row) for row in rows]

    async def create_operator_task(
        self,
        payload: OperatorTaskCreateRequest,
        *,
        actor_id: UUID,
    ) -> OperatorTaskView:
        self._require_round17_leo_actor(actor_id)
        now = self._now()
        task_id = uuid7()
        async with self._engine.begin() as connection:
            operator_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT actor_id FROM round17_staff_binding
                                WHERE display_name='yinzi'
                                  AND responsibility='SOURCE_OPERATOR'
                                  AND local_identity=false
                                ORDER BY actor_id"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            if len(operator_rows) != 1:
                raise OperationsRejected(
                    "Round 17 requires exactly one controlled yinzi operator binding"
                )
            assigned_to = operator_rows[0]["actor_id"]
            window_ready = await connection.scalar(
                text(
                    """SELECT 1 FROM round17_pilot_window window_row
                        WHERE window_row.id=:window
                          AND window_row.state='RUNNING'
                          AND :now>=window_row.started_at
                          AND :now<window_row.ends_at"""
                ),
                {"window": payload.window_id, "now": now},
            )
            source_ready = True
            if payload.source_id is not None:
                source_ready = bool(
                    await connection.scalar(
                        text(
                            """SELECT 1 FROM round17_pilot_window_source segment
                                WHERE segment.window_id=:window
                                  AND segment.source_id=:source
                                LIMIT 1"""
                        ),
                        {"window": payload.window_id, "source": payload.source_id},
                    )
                )
            if not window_ready or not source_ready:
                raise OperationsRejected(
                    "operator task must belong to the running Round 17 source cohort"
                )
            await connection.execute(
                text(
                    """INSERT INTO round17_operator_task(
                         id,window_id,source_id,category,assigned_to,status,
                         created_by,created_at,version
                       ) VALUES (
                         :id,:window,:source,:category,:assigned,'PENDING',
                         :created_by,:created_at,1
                       )"""
                ),
                {
                    "id": task_id,
                    "window": payload.window_id,
                    "source": payload.source_id,
                    "category": payload.category.value,
                    "assigned": assigned_to,
                    "created_by": actor_id,
                    "created_at": now,
                },
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_OPERATOR_TASK_CREATED',"
                    ":actor,'ROUND17_OPERATOR_TASK',:task,NULL,"
                    "jsonb_build_object('status','PENDING','category',:category,"
                    "'source_id',:source),:reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "task": task_id,
                    "category": payload.category.value,
                    "source": payload.source_id,
                    "reason": payload.reason,
                    "request_id": f"round17-operator-task-create:{task_id}",
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_task WHERE id=:id"),
                        {"id": task_id},
                    )
                )
                .mappings()
                .one()
            )
        return _operator_task_view(row)

    async def complete_operator_task(
        self,
        task_id: UUID,
        payload: OperatorTaskCompleteRequest,
        *,
        actor_id: UUID,
    ) -> OperatorTaskView:
        self._require_round17_leo_actor(actor_id)
        now = self._now()
        async with self._engine.begin() as connection:
            completed_id = await connection.scalar(
                text(
                    "SELECT complete_round17_operator_task("
                    ":task,:expected_version,:actor,:now)"
                ),
                {
                    "task": task_id,
                    "expected_version": payload.expected_version,
                    "actor": actor_id,
                    "now": now,
                },
            )
            if completed_id != task_id:
                raise OperationsRejected("operator task completion was not persisted")
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_OPERATOR_TASK_COMPLETED',"
                    ":actor,'ROUND17_OPERATOR_TASK',:task,"
                    "jsonb_build_object('status','IN_PROGRESS'),"
                    "jsonb_build_object('status','COMPLETED'),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "actor": actor_id,
                    "task": task_id,
                    "reason": payload.reason,
                    "request_id": (
                        f"round17-operator-task-complete:{task_id}:"
                        f"{payload.expected_version}"
                    ),
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_task WHERE id=:id"),
                        {"id": task_id},
                    )
                )
                .mappings()
                .one()
            )
        return _operator_task_view(row)

    async def start_work_session(
        self, *, actor_id: UUID, task_id: UUID
    ) -> OperatorWorkSessionView:
        now = self._now()
        session_id = uuid7()
        async with self._engine.begin() as connection:
            started_id = await connection.scalar(
                text(
                    "SELECT start_round17_operator_task(:task,:session,:actor,:now)"
                ),
                {
                    "task": task_id,
                    "session": session_id,
                    "actor": actor_id,
                    "now": now,
                },
            )
            if started_id != session_id:
                raise OperationsRejected(
                    "operator task session was not persisted"
                )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_work_session WHERE id=:id"),
                        {"id": session_id},
                    )
                )
                .mappings()
                .one()
            )
        return _work_session_view(row)

    async def heartbeat_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionHeartbeatRequest,
        *,
        actor_id: UUID,
    ) -> OperatorWorkSessionView:
        now = self._now()
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(
                            """SELECT session.*,window.ends_at AS window_ends_at
                                 FROM round17_operator_work_session session
                                 JOIN round17_pilot_window window ON window.id=session.window_id
                                WHERE session.id=:id AND session.actor_id=:actor
                                  AND session.stopped_at IS NULL
                                  AND window.state='RUNNING'
                                  AND :now < window.ends_at
                                FOR UPDATE OF session"""
                        ),
                        {"id": session_id, "actor": actor_id, "now": now},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is None or current["version"] != payload.expected_version:
                raise OperationsRejected("operator work heartbeat is stale or unauthorized")
            accrued = min(
                43_200,
                int(current["accrued_seconds"])
                + _bounded_active_seconds(current["last_activity_at"], now),
            )
            await connection.execute(
                text(
                    """UPDATE round17_operator_work_session
                          SET last_activity_at=:now,accrued_seconds=:seconds,
                              version=version+1
                        WHERE id=:id"""
                ),
                {"id": session_id, "now": now, "seconds": accrued},
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_work_session WHERE id=:id"),
                        {"id": session_id},
                    )
                )
                .mappings()
                .one()
            )
        return _work_session_view(row)

    async def stop_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionStopRequest,
        *,
        actor_id: UUID,
    ) -> OperatorWorkSessionView:
        now = self._now()
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(
                            """SELECT session.*,window.ends_at AS window_ends_at
                                 FROM round17_operator_work_session session
                                 JOIN round17_pilot_window window ON window.id=session.window_id
                                WHERE session.id=:id AND session.actor_id=:actor
                                FOR UPDATE OF session"""
                        ),
                        {"id": session_id, "actor": actor_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                raise OperationsRejected("operator work session does not exist")
            if current["stopped_at"] is None:
                if current["version"] != payload.expected_version:
                    raise OperationsRejected("operator work session version conflict")
                effective_stop = min(now, current["window_ends_at"])
                active_seconds = min(
                    43_200,
                    int(current["accrued_seconds"])
                    + _bounded_active_seconds(current["last_activity_at"], effective_stop),
                )
                await connection.execute(
                    text(
                        """UPDATE round17_operator_work_session
                              SET stopped_at=:now,active_seconds=:seconds,
                                  accrued_seconds=:seconds,version=version+1
                            WHERE id=:id"""
                    ),
                    {
                        "id": session_id,
                        "now": now,
                        "seconds": active_seconds,
                    },
                )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_work_session WHERE id=:id"),
                        {"id": session_id},
                    )
                )
                .mappings()
                .one()
            )
        return _work_session_view(row)

    async def correct_work_session(
        self,
        session_id: UUID,
        payload: OperatorWorkSessionCorrectionRequest,
        *,
        reviewer_id: UUID,
    ) -> OperatorWorkSessionView:
        self._require_round17_leo_actor(reviewer_id)
        now = self._now()
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(
                            """SELECT session.*,window.ends_at AS window_ends_at
                                 FROM round17_operator_work_session session
                                 JOIN round17_pilot_window window ON window.id=session.window_id
                                 JOIN round17_staff_binding operator_binding
                                   ON operator_binding.actor_id=session.actor_id
                                  AND operator_binding.display_name='yinzi'
                                  AND operator_binding.responsibility='SOURCE_OPERATOR'
                                  AND operator_binding.local_identity=false
                                 JOIN round17_staff_binding reviewer_binding
                                   ON reviewer_binding.actor_id=:reviewer
                                  AND reviewer_binding.display_name='LEO'
                                  AND reviewer_binding.responsibility='SOURCE_APPROVER'
                                  AND reviewer_binding.local_identity=false
                                WHERE session.id=:id
                                  AND session.actor_id<>:reviewer
                                FOR UPDATE OF session"""
                        ),
                        {"id": session_id, "reviewer": reviewer_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if (
                current is None
                or current["stopped_at"] is None
                or current["version"] != payload.expected_version
            ):
                raise OperationsRejected("operator work correction is stale or unauthorized")
            maximum_seconds = max(
                0,
                int(
                    (
                        min(current["stopped_at"], current["window_ends_at"])
                        - current["started_at"]
                    ).total_seconds()
                ),
            )
            if payload.active_seconds > min(43_200, maximum_seconds):
                raise OperationsRejected("operator work correction exceeds elapsed window time")
            await connection.execute(
                text(
                    """INSERT INTO round17_operator_work_correction (
                         id,session_id,actor_id,corrected_by,
                         previous_seconds,corrected_seconds,
                         reason_code,corrected_at
                       ) VALUES (
                         :id,:session,:actor,:reviewer,:previous,:corrected,:reason,:now
                       )"""
                ),
                {
                    "id": uuid7(),
                    "session": session_id,
                    "actor": current["actor_id"],
                    "reviewer": reviewer_id,
                    "previous": current["active_seconds"],
                    "corrected": payload.active_seconds,
                    "reason": payload.reason_code,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    """UPDATE round17_operator_work_session
                          SET active_seconds=:seconds,accrued_seconds=:seconds,
                              corrected=true,version=version+1
                        WHERE id=:id"""
                ),
                {"id": session_id, "seconds": payload.active_seconds},
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event(:audit,'ROUND17_OPERATOR_WORK_CORRECTED',"
                    ":reviewer,'ROUND17_OPERATOR_WORK_SESSION',:session,"
                    "jsonb_build_object('active_seconds',:previous),"
                    "jsonb_build_object('active_seconds',:corrected),"
                    ":reason,:request_id,:now)"
                ),
                {
                    "audit": uuid7(),
                    "reviewer": reviewer_id,
                    "session": session_id,
                    "previous": current["active_seconds"],
                    "corrected": payload.active_seconds,
                    "reason": payload.reason_code,
                    "request_id": (
                        f"round17-work-correction:{session_id}:"
                        f"{int(current['version']) + 1}"
                    ),
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM round17_operator_work_session WHERE id=:id"),
                        {"id": session_id},
                    )
                )
                .mappings()
                .one()
            )
        return _work_session_view(row)
