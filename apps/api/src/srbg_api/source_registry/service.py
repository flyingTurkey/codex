"""Single application service for source admission and raw-document registration."""

import logging
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from srbg_contracts import (
    AuthorityLevel,
    ConnectorConfigPreview,
    ConnectorConfigPreviewRequest,
    ConnectorConfigRequest,
    ConnectorConfigVersionView,
    ConnectorDefinitionView,
    CreateSourceRequest,
    DocumentDetail,
    FixtureUploadResponse,
    RuntimeAuthorization,
    SourceAssessmentSubmission,
    SourceAuditEventView,
    SourceChannel,
    SourceContentDomain,
    SourceCoverageMatrix,
    SourceDeclaredRole,
    SourceDetail,
    SourceEligibility,
    SourceGovernanceMetadataUpdate,
    SourceIndustry,
    SourceLifecycleAction,
    SourceLifecycleEventView,
    SourceLifecycleState,
    SourceOnboardingSubmission,
    SourcePolicyDecisionRequest,
    SourcePolicySubmission,
    SourcePolicyV2Submission,
    SourcePolicyVersionView,
    SourceProductionApprovalRequest,
    SourceState,
    SourceSummary,
    SourceTransitionRequest,
    SourceTrialKind,
    SourceTrialQualitySummary,
    SourceTrialRunRequest,
    SourceTrialRunStatus,
    SourceTrialRunView,
    SourceType,
)

from srbg_api.acquisition.contracts import ExecutionDomain
from srbg_api.config import Settings
from srbg_api.connectors.config import (
    CONNECTOR_DEFINITIONS,
    ConnectorConfigRejected,
    ConnectorKind,
    ValidatedConnectorConfig,
    validate_connector_config,
)
from srbg_api.connectors.config import (
    preview_connector_config as build_connector_preview,
)
from srbg_api.connectors.replay import (
    ConnectorParseFailed,
    FixedFixtureTransport,
    FixedReplayExecutor,
    FixtureExchange,
    InMemoryEvidenceStore,
    ManualImportSubmission,
)
from srbg_api.database import create_database_engine
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.security import UploadRejected
from srbg_api.document_vault.service import DocumentVaultService, SourceVaultMetrics
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.observability import (
    CONNECTOR_CONFIG_VERSIONS,
    SOURCE_COVERAGE_GAP_CELLS,
    SOURCE_LIFECYCLE_STATE,
    SOURCE_POLICY_REJECTIONS,
    SOURCE_RUNTIME_AUTHORIZATION_MISMATCHES,
    SOURCE_TRIAL_QUALITY_COUNT,
    SOURCE_TRIAL_READY_RATIO_BPS,
    SOURCE_TRIAL_RUNS,
)
from srbg_api.pdf_processing.security import FileSecurityPolicy
from srbg_api.source_registry.admission import (
    REQUIRED_ONBOARDING_CHECKS,
    AdmissionRejected,
    build_onboarding_record,
    build_policy_record,
)
from srbg_api.source_registry.domain import (
    GateEvidence,
    InvalidLifecycleCommand,
    InvalidSourceTransition,
    LifecycleCommand,
    LifecycleGate,
    SourceGate,
    lifecycle_transition,
    runtime_authorization,
    transition_source,
)
from srbg_api.source_registry.repository import (
    FixtureReplayBundle,
    FixtureReplayCapture,
    OnboardingRow,
    PolicyRow,
    RepositoryConflict,
    SourceRow,
    SourceVaultRepository,
    canonical_json_hash,
    fixture_set_hash,
)

LOGGER = logging.getLogger("srbg.source_registry")


def _log_governance_action(
    *,
    event_name: str,
    action: str,
    outcome: str,
    reason_code: str,
    request_id: str,
    source_id: UUID | None = None,
    object_id: UUID | None = None,
    level: int = logging.INFO,
    **bounded_context: str | int,
) -> None:
    """Emit allowlisted operational context without user text or network data."""

    extra: dict[str, str | int] = {
        "event_name": event_name,
        "action": action,
        "outcome": outcome,
        "reason_code": reason_code,
        "request_id": request_id,
    }
    if source_id is not None:
        extra["source_id"] = str(source_id)
    if object_id is not None:
        extra["object_id"] = str(object_id)
    extra.update(bounded_context)
    LOGGER.log(level, "source_governance_action", extra=extra)


class SourceServiceRejected(ValueError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class SourceRegistryService:
    def __init__(
        self,
        repository: SourceVaultRepository,
        document_vault: DocumentVaultService,
    ) -> None:
        self._repository = repository
        self._document_vault = document_vault
        self.metrics = document_vault.metrics

    @property
    def document_vault(self) -> DocumentVaultService:
        return self._document_vault

    async def close(self) -> None:
        await self._repository.close()

    async def list_sources(self) -> list[SourceSummary]:
        rows = await self._repository.list_sources()
        summaries = [await self._summary(row) for row in rows]
        for lifecycle_state in SourceLifecycleState:
            SOURCE_LIFECYCLE_STATE.labels(lifecycle_state.value).set(
                sum(summary.lifecycle_state is lifecycle_state for summary in summaries)
            )
        SOURCE_RUNTIME_AUTHORIZATION_MISMATCHES.set(
            sum(
                row.lifecycle_state is SourceLifecycleState.ACTIVE
                and summary.runtime_authorization is not RuntimeAuthorization.PRODUCTION
                for row, summary in zip(rows, summaries, strict=True)
            )
        )
        return summaries

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        row = await self._repository.create_source(
            payload,
            actor_id=actor_id,
            request_id=request_id,
            now=_now(),
        )
        _log_governance_action(
            event_name="source_registered",
            action="REGISTER_SOURCE",
            outcome="SUCCEEDED",
            reason_code="SOURCE_REGISTERED",
            request_id=request_id,
            source_id=row.id,
        )
        return await self._detail(row)

    async def get_source(self, source_id: UUID) -> SourceDetail:
        return await self._detail(await self._repository.get_source(source_id))

    async def get_eligibility(self, source_id: UUID) -> SourceEligibility:
        # Keep the V1 evidence fields available for compatibility, but make the
        # effective flag use the same V2 server-authoritative calculation as the
        # source detail and scheduler-facing projection.
        return (await self._detail(await self._repository.get_source(source_id))).eligibility

    async def save_policy(
        self,
        source_id: UUID,
        payload: SourcePolicySubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        await self._repository.get_source(source_id)
        now = _now()
        try:
            document = build_policy_record(source_id, payload, actor_id, now)
        except AdmissionRejected as exc:
            raise SourceServiceRejected(str(exc), 422) from exc
        await self._repository.save_policy(
            source_id,
            policy_version=payload.policy_version,
            status=payload.status.value,
            document=document,
            document_sha256=canonical_json_hash(document),
            valid_until=payload.review.valid_until,
            actor_id=actor_id,
            request_id=request_id,
            now=now,
        )
        return await self.get_source(source_id)

    async def save_onboarding(
        self,
        source_id: UUID,
        payload: SourceOnboardingSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        source = await self._repository.get_source(source_id)
        policy = await self._repository.latest_policy(source_id)
        now = _now()
        if policy is None or not _policy_is_valid(policy, now):
            raise SourceServiceRejected("a current valid source policy is required")
        fixture_hashes = await self._repository.fixture_hashes(source.id)
        try:
            document = build_onboarding_record(
                source.id,
                policy.policy_version,
                payload,
                actor_id,
                now,
                fixture_hashes=fixture_hashes,
            )
        except AdmissionRejected as exc:
            raise SourceServiceRejected(str(exc), 422) from exc
        await self._repository.save_onboarding(
            source.id,
            policy.id,
            record=document,
            record_sha256=canonical_json_hash(document),
            fixture_count=int(document["sample_count"]),
            fixture_set_sha256=str(document["fixture_set_sha256"]),
            valid_until=payload.valid_until,
            actor_id=actor_id,
            request_id=request_id,
            now=now,
        )
        return await self.get_source(source_id)

    async def submit_policy_version(
        self,
        source_id: UUID,
        payload: SourcePolicyV2Submission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourcePolicyVersionView:
        await self._repository.get_source(source_id)
        try:
            policy_id = await self._repository.submit_policy_version(
                source_id,
                payload,
                actor_id=actor_id,
                request_id=request_id,
                now=_now(),
            )
        except Exception as exc:
            if exc.__class__.__module__.startswith(("sqlalchemy", "asyncpg")):
                SOURCE_POLICY_REJECTIONS.labels("SUBMISSION_REJECTED").inc()
                _log_governance_action(
                    event_name="source_policy_version",
                    action="SUBMIT_POLICY",
                    outcome="REJECTED",
                    reason_code="SUBMISSION_REJECTED",
                    request_id=request_id,
                    source_id=source_id,
                    level=logging.WARNING,
                )
                raise SourceServiceRejected("source policy submission was rejected") from exc
            raise
        _log_governance_action(
            event_name="source_policy_version",
            action="SUBMIT_POLICY",
            outcome="SUCCEEDED",
            reason_code="POLICY_VERSION_SUBMITTED",
            request_id=request_id,
            source_id=source_id,
            object_id=policy_id,
        )
        versions = await self._repository.list_policy_versions(source_id)
        return next(version for version in versions if version.id == policy_id)

    async def list_policy_versions(self, source_id: UUID) -> list[SourcePolicyVersionView]:
        await self._repository.get_source(source_id)
        return await self._repository.list_policy_versions(source_id)

    async def decide_policy_version(
        self,
        source_id: UUID,
        policy_id: UUID,
        payload: SourcePolicyDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourcePolicyVersionView:
        try:
            await self._repository.decide_policy_version(
                source_id,
                policy_id,
                payload.outcome,
                payload.reason,
                actor_id=actor_id,
                request_id=request_id,
                now=_now(),
            )
        except Exception as exc:
            if exc.__class__.__module__.startswith(("sqlalchemy", "asyncpg")):
                SOURCE_POLICY_REJECTIONS.labels("DECISION_REJECTED").inc()
                _log_governance_action(
                    event_name="source_policy_decision",
                    action="REVIEW_POLICY",
                    outcome="REJECTED",
                    reason_code="DECISION_REJECTED",
                    request_id=request_id,
                    source_id=source_id,
                    object_id=policy_id,
                    level=logging.WARNING,
                )
                raise SourceServiceRejected("source policy decision was rejected") from exc
            raise
        if payload.outcome.value == "REJECTED":
            SOURCE_POLICY_REJECTIONS.labels("REVIEWER_REJECTED").inc()
        decision_reason = (
            "REVIEWER_REJECTED"
            if payload.outcome.value == "REJECTED"
            else "REVIEWER_APPROVED"
        )
        _log_governance_action(
            event_name="source_policy_decision",
            action="REVIEW_POLICY",
            outcome=payload.outcome.value,
            reason_code=decision_reason,
            request_id=request_id,
            source_id=source_id,
            object_id=policy_id,
            level=(
                logging.WARNING
                if payload.outcome.value == "REJECTED"
                else logging.INFO
            ),
        )
        versions = await self._repository.list_policy_versions(source_id)
        return next(version for version in versions if version.id == policy_id)

    async def start_trial_run(
        self,
        source_id: UUID,
        payload: SourceTrialRunRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceTrialRunView:
        source = await self._repository.get_source(source_id)
        gate = await self._lifecycle_gate(source_id)
        command = (
            LifecycleCommand.START_FIXTURE_TRIAL
            if payload.kind is SourceTrialKind.FIXTURE_REPLAY
            else LifecycleCommand.START_LIVE_TRIAL
        )
        try:
            lifecycle_transition(source.lifecycle_state, command, gate, actor_id=actor_id)
            trial_id = await self._repository.start_trial_run(
                source_id,
                payload,
                actor_id=actor_id,
                request_id=request_id,
                now=_now(),
            )
        except InvalidLifecycleCommand as exc:
            SOURCE_TRIAL_RUNS.labels(payload.kind.value, "rejected").inc()
            _log_governance_action(
                event_name="source_trial_started",
                action="START_TRIAL",
                outcome="REJECTED",
                reason_code="LIFECYCLE_GATE_REJECTED",
                request_id=request_id,
                source_id=source_id,
                level=logging.WARNING,
                trial_kind=payload.kind.value,
            )
            raise SourceServiceRejected(str(exc)) from exc
        except Exception as exc:
            if _is_repository_rejection(exc):
                SOURCE_TRIAL_RUNS.labels(
                    payload.kind.value, "security_failed"
                ).inc()
                _log_governance_action(
                    event_name="source_trial_started",
                    action="START_TRIAL",
                    outcome="REJECTED",
                    reason_code="TRIAL_AUTHORIZATION_REJECTED",
                    request_id=request_id,
                    source_id=source_id,
                    level=logging.WARNING,
                    trial_kind=payload.kind.value,
                )
                raise SourceServiceRejected("source trial authorization was rejected") from exc
            raise
        SOURCE_TRIAL_RUNS.labels(payload.kind.value, "pending").inc()
        _log_governance_action(
            event_name="source_trial_started",
            action="START_TRIAL",
            outcome="PENDING",
            reason_code="TRIAL_STARTED",
            request_id=request_id,
            source_id=source_id,
            object_id=trial_id,
            trial_kind=payload.kind.value,
        )
        trials = await self._repository.list_trial_runs(source_id)
        return next(trial for trial in trials if trial.id == trial_id)

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
    ) -> SourceTrialRunView:
        try:
            source_id, kind = await self._repository.complete_trial_run(
                trial_id,
                status,
                quality_summary,
                raw_namespace=raw_namespace,
                actor_id=actor_id,
                reason=reason,
                request_id=request_id,
                now=_now(),
            )
        except Exception as exc:
            if _is_repository_rejection(exc):
                SOURCE_TRIAL_RUNS.labels("UNKNOWN", "security_failed").inc()
                raise SourceServiceRejected("source trial result was rejected") from exc
            raise
        outcome = status.value.lower()
        SOURCE_TRIAL_RUNS.labels(kind.value, outcome).inc()
        for measure, value in (
            ("document_raw", quality_summary.raw_count),
            ("ready_document_raw", quality_summary.ready_count),
            ("parse_failed_document_raw", quality_summary.parse_failed_count),
            ("security_failed_total", quality_summary.security_failed_count),
            ("rejected_raw_attempt", quality_summary.rejected_raw_attempt_count),
        ):
            SOURCE_TRIAL_QUALITY_COUNT.labels(kind.value, outcome, measure).set(value)
        SOURCE_TRIAL_READY_RATIO_BPS.labels(kind.value, outcome).set(
            quality_summary.ready_ratio_bps
        )
        _log_governance_action(
            event_name="source_trial_completed",
            action="COMPLETE_TRIAL",
            outcome=status.value,
            reason_code=f"TRIAL_{status.value}",
            request_id=request_id,
            source_id=source_id,
            object_id=trial_id,
            level=(
                logging.INFO
                if status is SourceTrialRunStatus.SUCCEEDED
                else logging.WARNING
            ),
            trial_kind=kind.value,
            trial_status=status.value,
            ready_ratio_bps=quality_summary.ready_ratio_bps,
        )
        trials = await self._repository.list_trial_runs(source_id)
        return next(trial for trial in trials if trial.id == trial_id)

    async def complete_fixture_trial(
        self,
        source_id: UUID,
        trial_id: UUID,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceTrialRunView:
        """Close a fixture replay from database-derived evidence only.

        The client chooses neither the outcome nor the quality counts.  A replay
        succeeds only when every captured document-level raw object is READY and
        no rejected/security attempt exists; fixture success still never grants
        production authorization.
        """

        try:
            bundle = await self._repository.fixture_replay_bundle(source_id, trial_id)
            replay_status = bundle.replay_status
            if replay_status is None:
                replay_status = await self._evaluate_fixture_replay(
                    bundle,
                    actor_id=actor_id,
                )
            quality = await self._repository.fixture_trial_quality(source_id, trial_id)
        except Exception as exc:
            if _is_repository_rejection(exc):
                SOURCE_TRIAL_RUNS.labels("FIXTURE_REPLAY", "security_failed").inc()
                raise SourceServiceRejected("fixture trial completion was rejected") from exc
            raise
        succeeded = bool(
            replay_status == "PASSED"
            and quality.raw_count > 0
            and quality.ready_count == quality.raw_count
            and quality.parse_failed_count == 0
            and quality.security_failed_count == 0
            and quality.rejected_raw_attempt_count == 0
        )
        return await self.complete_trial_run(
            trial_id,
            (
                SourceTrialRunStatus.SUCCEEDED
                if succeeded
                else SourceTrialRunStatus.FAILED
            ),
            quality,
            raw_namespace=f"fixture/{trial_id}/raw/",
            actor_id=actor_id,
            reason=reason,
            request_id=request_id,
        )

    async def _evaluate_fixture_replay(
        self,
        bundle: FixtureReplayBundle,
        *,
        actor_id: UUID,
    ) -> str:
        evaluated_at = _now()
        latest_by_url: dict[str, tuple[FixtureReplayCapture, bytes]] = {}
        for capture in bundle.captures:
            content = await self._document_vault.read_fixture_object(
                capture.object_key,
                expected_sha256=capture.content_sha256,
                expected_size=capture.byte_size,
            )
            latest_by_url[capture.final_url] = (capture, content)

        exchanges = tuple(
            FixtureExchange(
                url=url,
                status_code=capture.http_status,
                headers={
                    "content-type": capture.declared_mime,
                    **({} if capture.etag is None else {"etag": capture.etag}),
                    **(
                        {}
                        if capture.last_modified is None
                        else {"last-modified": capture.last_modified}
                    ),
                },
                content=content,
            )
            for url, (capture, content) in latest_by_url.items()
        )
        transport = FixedFixtureTransport(exchanges)
        executor = FixedReplayExecutor(
            transport=transport,
            store=InMemoryEvidenceStore(),
            now=lambda: evaluated_at,
        )
        document_count = 0
        replay_status = "FAILED"
        reason_code = "CONNECTOR_REPLAY_FAILED"
        try:
            kind = ConnectorKind(bundle.connector_type)
            manual_imports = (
                tuple(
                    ManualImportSubmission.for_file(
                        canonical_url=url,
                        title=capture.title or capture.filename,
                        filename=capture.filename,
                        declared_mime=capture.declared_mime,
                        content=content,
                    )
                    for url, (capture, content) in latest_by_url.items()
                )
                if kind is ConnectorKind.MANUAL_IMPORT
                else ()
            )
            result = await executor.run(
                kind,
                bundle.config_document,
                source_allowed_hosts=bundle.allowed_hosts,
                domain=ExecutionDomain.FIXTURE,
                manual_imports=manual_imports,
            )
            expected_urls = set(latest_by_url)
            if kind is ConnectorKind.MANUAL_IMPORT:
                if transport.calls:
                    raise ConnectorParseFailed("manual replay attempted fixture transport I/O")
            elif set(transport.calls) != expected_urls:
                raise ConnectorParseFailed("fixture exchange set was not consumed exactly")
            expected_hashes = {
                capture.content_sha256 for capture, _content in latest_by_url.values()
            }
            if (
                transport.real_network_calls != 0
                or not result.document_versions
                or any(
                    version.content_sha256 not in expected_hashes
                    for version in result.document_versions
                )
                or any(raw.content_sha256 not in expected_hashes for raw in result.raw_objects)
            ):
                raise ConnectorParseFailed("fixture replay evidence does not match captures")
            document_count = len(result.document_versions)
            replay_status = "PASSED"
            reason_code = "CONNECTOR_REPLAY_PASSED"
        except (
            ConnectorConfigRejected,
            ConnectorParseFailed,
            OSError,
            PermissionError,
            UploadRejected,
            ValueError,
        ):
            replay_status = "FAILED"
            reason_code = "CONNECTOR_REPLAY_FAILED"

        await self._repository.record_fixture_replay_result(
            bundle,
            status=replay_status,
            reason_code=reason_code,
            document_count=document_count,
            transport_call_count=len(transport.calls),
            actor_id=actor_id,
            now=evaluated_at,
        )
        return replay_status

    async def list_trial_runs(self, source_id: UUID) -> list[SourceTrialRunView]:
        await self._repository.get_source(source_id)
        return await self._repository.list_trial_runs(source_id)

    async def approve_production(
        self,
        source_id: UUID,
        payload: SourceProductionApprovalRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        source = await self._repository.get_source(source_id)
        gate = replace(
            await self._lifecycle_gate(source_id),
            production_approval_current=True,
        )
        try:
            lifecycle_transition(
                source.lifecycle_state,
                LifecycleCommand.APPROVE_PRODUCTION,
                gate,
                actor_id=actor_id,
            )
            await self._repository.approve_production(
                source_id,
                policy_version_id=payload.policy_version_id,
                connector_config_version_id=payload.connector_config_version_id,
                trial_run_id=payload.trial_run_id,
                reason=payload.reason,
                actor_id=actor_id,
                request_id=request_id,
                now=_now(),
            )
        except InvalidLifecycleCommand as exc:
            raise SourceServiceRejected(str(exc)) from exc
        except Exception as exc:
            if _is_repository_rejection(exc):
                raise SourceServiceRejected("source production approval was rejected") from exc
            raise
        return await self.get_source(source_id)

    async def lifecycle_action(
        self,
        source_id: UUID,
        action: str,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        try:
            command = LifecycleCommand(action)
        except ValueError as exc:
            _log_governance_action(
                event_name="source_lifecycle_action",
                action="UNSUPPORTED",
                outcome="REJECTED",
                reason_code="UNSUPPORTED_LIFECYCLE_COMMAND",
                request_id=request_id,
                source_id=source_id,
                level=logging.WARNING,
            )
            raise SourceServiceRejected("unsupported lifecycle command", 422) from exc
        source = await self._repository.get_source(source_id)
        gate = await self._lifecycle_gate(source_id)
        try:
            lifecycle_transition(source.lifecycle_state, command, gate, actor_id=actor_id)
            await self._repository.apply_lifecycle_action(
                source_id,
                action,
                reason,
                actor_id=actor_id,
                request_id=request_id,
                now=_now(),
            )
        except InvalidLifecycleCommand as exc:
            _log_governance_action(
                event_name="source_lifecycle_action",
                action=action,
                outcome="REJECTED",
                reason_code="LIFECYCLE_GATE_REJECTED",
                request_id=request_id,
                source_id=source_id,
                level=logging.WARNING,
            )
            raise SourceServiceRejected(str(exc)) from exc
        except Exception as exc:
            if _is_repository_rejection(exc):
                _log_governance_action(
                    event_name="source_lifecycle_action",
                    action=action,
                    outcome="REJECTED",
                    reason_code="DATABASE_GATE_REJECTED",
                    request_id=request_id,
                    source_id=source_id,
                    level=logging.WARNING,
                )
                raise SourceServiceRejected("source lifecycle command was rejected") from exc
            raise
        _log_governance_action(
            event_name="source_lifecycle_action",
            action=action,
            outcome="SUCCEEDED",
            reason_code="LIFECYCLE_TRANSITION_RECORDED",
            request_id=request_id,
            source_id=source_id,
        )
        return await self.get_source(source_id)

    async def list_lifecycle_events(self, source_id: UUID) -> list[SourceLifecycleEventView]:
        await self._repository.get_source(source_id)
        return await self._repository.list_lifecycle_events(source_id)

    async def list_audit_events(self, source_id: UUID) -> list[SourceAuditEventView]:
        await self._repository.get_source(source_id)
        rows = await self._repository.list_audit_events(source_id)
        return [SourceAuditEventView.model_validate(row) for row in rows]

    async def source_coverage(self) -> SourceCoverageMatrix:
        matrix = await self._repository.source_coverage(now=_now())
        SOURCE_COVERAGE_GAP_CELLS.set(matrix.gap_cell_count)
        if matrix.gap_cell_count:
            _log_governance_action(
                event_name="source_coverage_evaluated",
                action="EVALUATE_COVERAGE",
                outcome="GAPS_DETECTED",
                reason_code="COVERAGE_GAPS_PRESENT",
                request_id="system-metric-collection",
                level=logging.WARNING,
                gap_cell_count=matrix.gap_cell_count,
            )
        return matrix

    async def list_connector_definitions(self) -> list[ConnectorDefinitionView]:
        return await self._repository.list_connector_definitions()

    async def preview_connector_config(
        self, source_id: UUID, payload: ConnectorConfigPreviewRequest
    ) -> ConnectorConfigPreview:
        _, validated, allowed_hosts = await self._validated_connector(source_id, payload)
        preview = build_connector_preview(
            ConnectorKind(payload.connector_type.value),
            payload.config,
            source_allowed_hosts=allowed_hosts,
        )
        if preview["schema_sha256"] != validated.schema_sha256:
            raise SourceServiceRejected("connector definition changed during preview")
        return ConnectorConfigPreview.model_validate(preview)

    async def save_connector_config(
        self,
        source_id: UUID,
        payload: ConnectorConfigRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> ConnectorConfigVersionView:
        try:
            definition, validated, _ = await self._validated_connector(source_id, payload)
            persisted = validated.document
            credential = persisted.pop("credential_ref", None)
            credential_ref = credential if isinstance(credential, str) else None
            host_value = persisted.get("allowed_hosts")
            if not isinstance(host_value, list) or not all(
                isinstance(host, str) for host in host_value
            ):
                raise ConnectorConfigRejected("validated connector hosts are invalid")
            config_id = await self._repository.save_connector_config(
                source_id,
                definition_id=definition.id,
                config_document=persisted,
                credential_ref=credential_ref,
                actor_id=actor_id,
                reason=payload.reason,
                request_id=request_id,
                now=_now(),
            )
        except ConnectorConfigRejected as exc:
            CONNECTOR_CONFIG_VERSIONS.labels(payload.connector_type.value, "rejected").inc()
            _log_governance_action(
                event_name="connector_config_version",
                action="SAVE_CONNECTOR_CONFIG",
                outcome="REJECTED",
                reason_code="CONFIG_VALIDATION_REJECTED",
                request_id=request_id,
                source_id=source_id,
                level=logging.WARNING,
                connector_type=payload.connector_type.value,
            )
            raise SourceServiceRejected(str(exc), 422) from exc
        except SourceServiceRejected:
            CONNECTOR_CONFIG_VERSIONS.labels(payload.connector_type.value, "rejected").inc()
            _log_governance_action(
                event_name="connector_config_version",
                action="SAVE_CONNECTOR_CONFIG",
                outcome="REJECTED",
                reason_code="CONFIG_VALIDATION_REJECTED",
                request_id=request_id,
                source_id=source_id,
                level=logging.WARNING,
                connector_type=payload.connector_type.value,
            )
            raise
        except Exception as exc:
            if exc.__class__.__module__.startswith(("sqlalchemy", "asyncpg")):
                CONNECTOR_CONFIG_VERSIONS.labels(
                    payload.connector_type.value, "conflict"
                ).inc()
                _log_governance_action(
                    event_name="connector_config_version",
                    action="SAVE_CONNECTOR_CONFIG",
                    outcome="REJECTED",
                    reason_code="CONFIG_PERSISTENCE_CONFLICT",
                    request_id=request_id,
                    source_id=source_id,
                    level=logging.WARNING,
                    connector_type=payload.connector_type.value,
                )
                raise SourceServiceRejected(
                    "connector configuration version was rejected"
                ) from exc
            raise
        CONNECTOR_CONFIG_VERSIONS.labels(payload.connector_type.value, "valid").inc()
        _log_governance_action(
            event_name="connector_config_version",
            action="SAVE_CONNECTOR_CONFIG",
            outcome="SUCCEEDED",
            reason_code="CONFIG_VERSION_SAVED",
            request_id=request_id,
            source_id=source_id,
            object_id=config_id,
            connector_type=payload.connector_type.value,
        )
        configs = await self._repository.list_connector_configs(source_id)
        return next(config for config in configs if config.id == config_id)

    async def list_connector_configs(
        self, source_id: UUID
    ) -> list[ConnectorConfigVersionView]:
        await self._repository.get_source(source_id)
        return await self._repository.list_connector_configs(source_id)

    async def update_governance_metadata(
        self,
        source_id: UUID,
        payload: SourceGovernanceMetadataUpdate,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        await self._repository.get_source(source_id)
        await self._repository.update_governance_metadata(
            source_id,
            payload,
            actor_id=actor_id,
            request_id=request_id,
            now=_now(),
        )
        return await self.get_source(source_id)

    async def append_assessments(
        self,
        source_id: UUID,
        payload: SourceAssessmentSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        await self._repository.get_source(source_id)
        await self._repository.append_assessments(
            source_id,
            payload,
            actor_id=actor_id,
            request_id=request_id,
            now=_now(),
        )
        return await self.get_source(source_id)

    async def _validated_connector(
        self,
        source_id: UUID,
        payload: ConnectorConfigPreviewRequest,
    ) -> tuple[ConnectorDefinitionView, ValidatedConnectorConfig, tuple[str, ...]]:
        await self._repository.get_source(source_id)
        try:
            kind = ConnectorKind(payload.connector_type.value)
            database_definition = await self._repository.connector_definition(
                payload.connector_type, payload.definition_version
            )
            builtin = CONNECTOR_DEFINITIONS[kind]
            if (
                database_definition.definition_version != builtin.definition_version
                or database_definition.schema_version != builtin.schema_version
                or database_definition.schema_sha256 != builtin.schema_sha256
                or database_definition.executor_key != builtin.executor_key
            ):
                raise ConnectorConfigRejected("connector definition is not server-approved")
            allowed_hosts = await self._repository.current_policy_allowed_hosts(
                source_id, now=_now()
            )
            validated = validate_connector_config(
                kind,
                payload.config,
                source_allowed_hosts=allowed_hosts,
            )
        except ConnectorConfigRejected as exc:
            raise SourceServiceRejected(str(exc), 422) from exc
        except RepositoryConflict as exc:
            raise SourceServiceRejected(str(exc)) from exc
        return database_definition, validated, allowed_hosts

    async def transition(
        self,
        source_id: UUID,
        payload: SourceTransitionRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        source = await self._repository.get_source(source_id)
        gate, _ = await self._gate(source_id)
        try:
            target = transition_source(source.state, payload.target_state, gate)
        except InvalidSourceTransition as exc:
            raise SourceServiceRejected(str(exc)) from exc
        await self._repository.change_source(
            source_id,
            state=target,
            enabled=False,
            event_type="SOURCE_STATE_TRANSITIONED",
            reason=payload.reason,
            actor_id=actor_id,
            request_id=request_id,
            now=_now(),
        )
        return await self.get_source(source_id)

    async def set_enabled(
        self,
        source_id: UUID,
        enabled: bool,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail:
        source = await self._repository.get_source(source_id)
        gate, _ = await self._gate(source_id)
        target_state = source.state
        if enabled:
            if source.state is SourceState.APPROVED:
                try:
                    target_state = transition_source(source.state, SourceState.ACTIVE, gate)
                except InvalidSourceTransition as exc:
                    raise SourceServiceRejected(str(exc)) from exc
            elif source.state is not SourceState.ACTIVE or not gate.allows_approval():
                raise SourceServiceRejected("source admission evidence is not complete")
        await self._repository.change_source(
            source_id,
            state=target_state,
            enabled=enabled,
            event_type="SOURCE_ENABLED" if enabled else "SOURCE_DISABLED",
            reason=reason,
            actor_id=actor_id,
            request_id=request_id,
            now=_now(),
        )
        return await self.get_source(source_id)

    async def upload_fixture(
        self,
        source_id: UUID,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        canonical_url: str,
        actor_id: UUID,
        request_id: str,
    ) -> FixtureUploadResponse:
        return await self._document_vault.upload(
            source_id,
            content=content,
            filename=filename,
            declared_mime=declared_mime,
            canonical_url=canonical_url,
            actor_id=actor_id,
            request_id=request_id,
            acquired_at=_now(),
        )

    async def get_document(self, document_id: UUID) -> DocumentDetail:
        return await self._repository.get_document(document_id)

    async def _summary(self, source: SourceRow) -> SourceSummary:
        _, fixture_hashes = await self._gate(source.id)
        lifecycle_gate = await self._lifecycle_gate(source.id)
        authorization = runtime_authorization(source.lifecycle_state, lifecycle_gate)
        return SourceSummary(
            id=source.id,
            registry_code=source.registry_code,
            name=source.name,
            base_url=source.base_url,
            channel=SourceChannel(source.channel),
            source_type=SourceType(source.source_type),
            authority_level=AuthorityLevel(source.authority_level),
            priority=source.priority,
            state=source.state,
            enabled=source.enabled,
            effective_active=authorization is RuntimeAuthorization.PRODUCTION,
            fixture_count=len(set(fixture_hashes)),
            created_at=source.created_at,
            lifecycle_state=source.lifecycle_state,
            runtime_authorization=authorization,
            available_actions=_available_actions(source.lifecycle_state, lifecycle_gate),
            governance_owner_id=source.governance_owner_id,
            country_codes=list(source.country_codes),
            region_codes=list(source.region_codes),
            language_tags=list(source.language_tags),
            industries=[SourceIndustry(value) for value in source.industries],
            content_domains=[SourceContentDomain(value) for value in source.content_domains],
            declared_roles=[SourceDeclaredRole(value) for value in source.declared_roles],
        )

    async def _detail(self, source: SourceRow) -> SourceDetail:
        summary = await self._summary(source)
        gate, fixture_hashes = await self._gate(source.id)
        eligibility = _eligibility(source, gate, fixture_hashes).model_copy(
            update={"effective_active": summary.effective_active}
        )
        authority, independence = await self._repository.latest_assessments(source.id)
        return SourceDetail(
            **summary.model_dump(),
            collection_method=source.collection_method,
            poll_interval_minutes=source.poll_interval_minutes,
            owner=source.owner,
            eligibility=eligibility,
            source_authority=authority,
            source_independence=independence,
            current_policy_version_id=source.current_policy_version_id,
            current_connector_config_version_id=source.current_connector_config_version_id,
            current_trial_run_id=source.current_trial_run_id,
        )

    async def _lifecycle_gate(self, source_id: UUID) -> LifecycleGate:
        facts = await self._repository.lifecycle_facts(source_id, now=_now())
        return LifecycleGate(
            policy_valid=facts.policy_valid,
            policy_valid_until=facts.policy_valid_until,
            robots_allowed=facts.robots_allowed,
            terms_allowed=facts.terms_allowed,
            copyright_allowed=facts.copyright_allowed,
            governance_owner_present=facts.governance_owner_present,
            compliance_approved=facts.compliance_approved,
            connector_config_current=facts.connector_config_current,
            trial_kind=facts.trial_kind,
            live_trial_succeeded=facts.live_trial_succeeded,
            production_approval_current=facts.production_approval_current,
            separation_actor_ids=facts.separation_actor_ids,
            current_trial_pending=facts.current_trial_pending,
        )

    async def _gate(self, source_id: UUID) -> tuple[SourceGate, list[str]]:
        policy = await self._repository.latest_policy(source_id)
        onboarding = await self._repository.latest_onboarding(source_id)
        fixture_hashes = await self._repository.fixture_hashes(source_id)
        now = _now()
        policy_valid = policy is not None and _policy_is_valid(policy, now)
        onboarding_valid = onboarding is not None and _onboarding_is_valid(onboarding, now)
        policy_matches = bool(
            policy is not None
            and onboarding is not None
            and onboarding.source_policy_id == policy.id
            and onboarding.record.get("source_policy_version") == policy.policy_version
        )
        checks_complete = bool(onboarding is not None and _checks_complete(onboarding.record))
        current_fixture_hash = fixture_set_hash(fixture_hashes)
        evidence_fixture_count = 0 if onboarding is None else onboarding.fixture_count
        fixture_set_matches = bool(
            onboarding is not None
            and onboarding.fixture_set_sha256 == current_fixture_hash
            and evidence_fixture_count == len(set(fixture_hashes))
        )
        gate = SourceGate(
            policy_valid=policy_valid,
            policy_valid_until=None if policy is None else policy.valid_until,
            onboarding_valid=onboarding_valid,
            onboarding_valid_until=None if onboarding is None else onboarding.valid_until,
            onboarding_policy_matches=policy_matches,
            required_checks_complete=checks_complete,
            fixture_count=len(set(fixture_hashes)) if fixture_set_matches else 0,
        )
        return gate, fixture_hashes


def build_default_source_service(settings: Settings) -> SourceRegistryService:
    engine = create_database_engine(settings)
    repository = SourceVaultRepository(engine)
    metrics = SourceVaultMetrics()
    vault = DocumentVaultService(
        repository=repository,
        object_store=S3ObjectStore(settings),
        malware_scanner=ClamAVScanner(
            settings.clamav_host,
            settings.clamav_port,
            settings.external_io_timeout_seconds,
        ),
        metrics=metrics,
        max_fixture_bytes=settings.fixture_max_bytes,
        max_pdf_pages=settings.fixture_max_pdf_pages,
        file_security_policy=_file_security_policy(settings),
    )
    return SourceRegistryService(repository, vault)


def _file_security_policy(settings: Settings) -> FileSecurityPolicy:
    return FileSecurityPolicy(
        max_file_bytes=settings.fixture_max_bytes,
        max_pdf_pages=settings.fixture_max_pdf_pages,
        max_ocr_pages=settings.pdf_max_ocr_pages,
        max_zip_entries=settings.attachment_max_entries,
        max_uncompressed_bytes=settings.attachment_max_uncompressed_bytes,
        max_compression_ratio=settings.attachment_max_compression_ratio,
        max_page_pixels=settings.pdf_max_page_pixels,
    )


def _eligibility(
    source: SourceRow,
    gate: SourceGate,
    fixture_hashes: list[str],
) -> SourceEligibility:
    checks = (
        (gate.policy_valid, "VALID_POLICY_REQUIRED"),
        (gate.onboarding_valid, "VALID_ONBOARDING_RECORD_REQUIRED"),
        (gate.onboarding_policy_matches, "ONBOARDING_POLICY_MISMATCH"),
        (gate.required_checks_complete, "REQUIRED_CHECKS_INCOMPLETE"),
        (gate.fixture_count >= 30, "THIRTY_DISTINCT_FIXTURES_REQUIRED"),
    )
    missing = [reason for passed, reason in checks if not passed]
    effective = GateEvidence(
        state=source.state,
        enabled=source.enabled,
        gate=gate,
    ).is_effectively_active()
    return SourceEligibility(
        effective_active=effective,
        policy_valid=gate.policy_valid,
        onboarding_valid=gate.onboarding_valid,
        onboarding_policy_matches=gate.onboarding_policy_matches,
        required_checks_complete=gate.required_checks_complete,
        fixture_count=len(set(fixture_hashes)),
        required_fixture_count=30,
        fixture_set_sha256=fixture_set_hash(fixture_hashes) if fixture_hashes else None,
        missing_reasons=missing,
    )


def _policy_is_valid(policy: PolicyRow, now: datetime) -> bool:
    reviews = (
        policy.document.get("robots_review", {}),
        policy.document.get("terms_review", {}),
    )
    return bool(
        policy.status == "VALID"
        and policy.valid_until > now
        and policy.document_sha256 == canonical_json_hash(policy.document)
        and all(review.get("result") != "BLOCKED" for review in reviews)
        and all(len(str(review.get("evidence_sha256", ""))) == 64 for review in reviews)
    )


def _onboarding_is_valid(record: OnboardingRow, now: datetime) -> bool:
    return bool(
        record.valid_until > now
        and record.record.get("decision") == "APPROVED"
        and record.record_sha256 == canonical_json_hash(record.record)
    )


def _checks_complete(document: dict[str, Any]) -> bool:
    checks = document.get("checks", [])
    codes = [check.get("code") for check in checks if isinstance(check, dict)]
    return bool(
        len(codes) == len(set(codes))
        and set(codes) == REQUIRED_ONBOARDING_CHECKS
        and all(check.get("passed") is True for check in checks)
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _is_repository_rejection(exc: Exception) -> bool:
    return isinstance(exc, RepositoryConflict) or exc.__class__.__module__.startswith(
        ("sqlalchemy", "asyncpg")
    )


def _available_actions(
    state: SourceLifecycleState,
    gate: LifecycleGate,
) -> list[SourceLifecycleAction]:
    if state is SourceLifecycleState.RETIRED:
        return []
    if state is SourceLifecycleState.CANDIDATE:
        return [SourceLifecycleAction.SUBMIT_COMPLIANCE, SourceLifecycleAction.RETIRE]
    if state is SourceLifecycleState.COMPLIANCE_REVIEW:
        actions: list[SourceLifecycleAction] = [SourceLifecycleAction.RETIRE]
        if gate.allows_trial():
            actions[0:0] = [
                SourceLifecycleAction.START_FIXTURE_TRIAL,
                SourceLifecycleAction.START_LIVE_TRIAL,
            ]
        return actions
    if state is SourceLifecycleState.TRIAL:
        actions = [SourceLifecycleAction.RETIRE]
        if not gate.current_trial_pending and gate.allows_trial():
            actions[0:0] = [
                SourceLifecycleAction.START_FIXTURE_TRIAL,
                SourceLifecycleAction.START_LIVE_TRIAL,
            ]
        if replace(gate, production_approval_current=True).allows_production():
            actions.insert(0, SourceLifecycleAction.APPROVE_PRODUCTION)
        return actions
    if state is SourceLifecycleState.ACTIVE:
        return [SourceLifecycleAction.PAUSE]
    actions = [SourceLifecycleAction.RETIRE]
    if gate.allows_production():
        actions.insert(0, SourceLifecycleAction.RESUME)
    if gate.allows_trial():
        actions[0:0] = [
            SourceLifecycleAction.START_FIXTURE_TRIAL,
            SourceLifecycleAction.START_LIVE_TRIAL,
        ]
    return actions
