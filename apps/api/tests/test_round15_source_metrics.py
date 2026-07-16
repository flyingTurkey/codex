import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import srbg_api.source_registry.service as service_module
from srbg_api.connectors.config import CONNECTOR_DEFINITIONS, ConnectorKind
from srbg_api.document_vault.service import SourceVaultMetrics
from srbg_api.observability import (
    SOURCE_COVERAGE_GAP_CELLS,
    SOURCE_LIFECYCLE_STATE,
    SOURCE_RUNTIME_AUTHORIZATION_MISMATCHES,
)
from srbg_api.source_registry.repository import (
    LifecycleFacts,
    RepositoryConflict,
    SourceRow,
)
from srbg_api.source_registry.service import SourceRegistryService, SourceServiceRejected
from srbg_contracts import (
    ConnectorConfigRequest,
    ConnectorDefinitionView,
    ConnectorType,
    SourceContentDomain,
    SourceCoverageCell,
    SourceCoverageMatrix,
    SourceIndustry,
    SourceLifecycleState,
    SourcePolicyDecisionOutcome,
    SourcePolicyDecisionRequest,
    SourcePolicyVersionView,
    SourceState,
    SourceTrialKind,
    SourceTrialQualitySummary,
    SourceTrialRunRequest,
    SourceTrialRunStatus,
    SourceTrialRunView,
    SourceType,
)

SOURCE_ID = UUID("019b1500-0000-7000-8000-000000000201")
ACTOR_ID = UUID("019b1500-0000-7000-8000-000000000202")


class DummyVault:
    def __init__(self) -> None:
        self.metrics = SourceVaultMetrics()


class SpyCounter:
    def __init__(self) -> None:
        self.increments: list[tuple[str, ...]] = []
        self._labels: tuple[str, ...] = ()

    def labels(self, *labels: str) -> "SpyCounter":
        child = SpyCounter()
        child.increments = self.increments
        child._labels = tuple(labels)
        return child

    def inc(self) -> None:
        self.increments.append(self._labels)


class SpyGauge:
    def __init__(self) -> None:
        self.samples: list[tuple[tuple[str, ...], float]] = []
        self._labels: tuple[str, ...] = ()

    def labels(self, *labels: str) -> "SpyGauge":
        child = SpyGauge()
        child.samples = self.samples
        child._labels = tuple(labels)
        return child

    def set(self, value: float) -> None:
        self.samples.append((self._labels, value))


def _source(state: SourceLifecycleState) -> SourceRow:
    return SourceRow(
        id=SOURCE_ID,
        registry_code=None,
        name="Round 15 metrics source",
        base_url="https://example.test/",
        channel="BOTH",
        source_type=SourceType.GOVERNMENT.value,
        authority_level="A1",
        priority="P0",
        collection_method="manual",
        poll_interval_minutes=60,
        owner="source_ops",
        state=SourceState.CANDIDATE,
        enabled=False,
        lifecycle_state=state,
        trial_kind=None,
        registered_by=ACTOR_ID,
        governance_owner_id=ACTOR_ID,
        country_codes=("CN",),
        region_codes=("CN-SC",),
        language_tags=("zh-CN",),
        industries=(SourceIndustry.HIGHWAY.value,),
        content_domains=(SourceContentDomain.SAFETY_REGULATION.value,),
        declared_roles=("OFFICIAL_PRIMARY",),
        current_policy_version_id=None,
        current_connector_config_version_id=None,
        current_trial_run_id=None,
        created_at=datetime.now(UTC),
    )


def _facts(*, ready: bool) -> LifecycleFacts:
    return LifecycleFacts(
        policy_valid=ready,
        policy_valid_until=datetime.now(UTC) + timedelta(days=1) if ready else None,
        robots_allowed=ready,
        terms_allowed=ready,
        copyright_allowed=ready,
        governance_owner_present=ready,
        compliance_approved=ready,
        connector_config_current=ready,
        trial_kind=None,
        live_trial_succeeded=False,
        production_approval_current=False,
        separation_actor_ids=frozenset(),
    )


class MetricsRepository:
    async def list_sources(self) -> list[SourceRow]:
        return [_source(SourceLifecycleState.ACTIVE)]

    async def lifecycle_facts(self, source_id: UUID, *, now: datetime) -> LifecycleFacts:
        return _facts(ready=False)

    async def latest_policy(self, source_id: UUID) -> None:
        return None

    async def latest_onboarding(self, source_id: UUID) -> None:
        return None

    async def fixture_hashes(self, source_id: UUID) -> list[str]:
        return []

    async def source_coverage(self, *, now: datetime) -> SourceCoverageMatrix:
        return SourceCoverageMatrix(
            generated_at=now,
            cells=[
                SourceCoverageCell(
                    industry=SourceIndustry.HIGHWAY,
                    content_domain=SourceContentDomain.SAFETY_REGULATION,
                    source_type=SourceType.GOVERNMENT,
                    region="CN-SC",
                    language="zh-CN",
                    candidate_count=0,
                    trial_count=0,
                    active_count=0,
                    gap=True,
                )
            ],
            gap_cell_count=1,
        )


@pytest.mark.asyncio
async def test_lifecycle_authorization_and_coverage_gauges_use_business_results() -> None:
    service = SourceRegistryService(MetricsRepository(), DummyVault())  # type: ignore[arg-type]

    await service.list_sources()
    await service.source_coverage()

    assert SOURCE_LIFECYCLE_STATE.labels("ACTIVE")._value.get() == 1  # type: ignore[attr-defined]
    assert SOURCE_RUNTIME_AUTHORIZATION_MISMATCHES._value.get() == 1  # type: ignore[attr-defined]
    assert SOURCE_COVERAGE_GAP_CELLS._value.get() == 1  # type: ignore[attr-defined]


class TrialRepository:
    async def get_source(self, source_id: UUID) -> SourceRow:
        return _source(SourceLifecycleState.COMPLIANCE_REVIEW)

    async def lifecycle_facts(self, source_id: UUID, *, now: datetime) -> LifecycleFacts:
        return _facts(ready=True)

    async def start_trial_run(self, *args: object, **kwargs: object) -> UUID:
        raise RepositoryConflict("database gate rejected trial")


@pytest.mark.asyncio
async def test_trial_database_rejection_emits_security_failure_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counter = SpyCounter()
    monkeypatch.setattr(service_module, "SOURCE_TRIAL_RUNS", counter)
    service = SourceRegistryService(TrialRepository(), DummyVault())  # type: ignore[arg-type]
    payload = SourceTrialRunRequest(
        kind=SourceTrialKind.FIXTURE_REPLAY,
        policy_version_id=UUID("019b1500-0000-7000-8000-000000000203"),
        connector_config_version_id=UUID("019b1500-0000-7000-8000-000000000204"),
        reason="exercise the authoritative trial gate",
    )

    with pytest.raises(SourceServiceRejected):
        await service.start_trial_run(
            SOURCE_ID, payload, actor_id=ACTOR_ID, request_id="round15-metric-test"
        )

    assert counter.increments == [("FIXTURE_REPLAY", "security_failed")]


class CompletedTrialRepository:
    async def complete_trial_run(
        self, *args: object, **kwargs: object
    ) -> tuple[UUID, SourceTrialKind]:
        return SOURCE_ID, SourceTrialKind.FIXTURE_REPLAY

    async def list_trial_runs(self, source_id: UUID) -> list[SourceTrialRunView]:
        return [
            SourceTrialRunView(
                id=UUID("019b1500-0000-7000-8000-000000000208"),
                source_id=source_id,
                kind=SourceTrialKind.FIXTURE_REPLAY,
                status=SourceTrialRunStatus.SUCCEEDED,
                policy_version_id=UUID("019b1500-0000-7000-8000-000000000203"),
                connector_config_version_id=UUID(
                    "019b1500-0000-7000-8000-000000000204"
                ),
                requested_by=ACTOR_ID,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                quality_summary=SourceTrialQualitySummary(
                    raw_count=3,
                    ready_count=2,
                    parse_failed_count=0,
                    security_failed_count=1,
                    rejected_raw_attempt_count=1,
                    ready_ratio_bps=6667,
                ),
                created_at=datetime.now(UTC),
            )
        ]


@pytest.mark.asyncio
async def test_completed_trial_emits_database_quality_ratio_with_bounded_labels(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    counter = SpyCounter()
    count_gauge = SpyGauge()
    ratio_gauge = SpyGauge()
    monkeypatch.setattr(service_module, "SOURCE_TRIAL_RUNS", counter)
    monkeypatch.setattr(service_module, "SOURCE_TRIAL_QUALITY_COUNT", count_gauge)
    monkeypatch.setattr(
        service_module, "SOURCE_TRIAL_READY_RATIO_BPS", ratio_gauge
    )
    service = SourceRegistryService(
        CompletedTrialRepository(), DummyVault()  # type: ignore[arg-type]
    )
    quality = SourceTrialQualitySummary(
        raw_count=3,
        ready_count=2,
        parse_failed_count=0,
        security_failed_count=1,
        rejected_raw_attempt_count=1,
        ready_ratio_bps=6667,
    )

    trial_id = UUID("019b1500-0000-7000-8000-000000000208")
    with caplog.at_level(logging.INFO, logger="srbg.source_registry"):
        await service.complete_trial_run(
            trial_id,
            SourceTrialRunStatus.SUCCEEDED,
            quality,
            raw_namespace=(f"fixture/{trial_id}/raw/"),
            actor_id=ACTOR_ID,
            reason="complete the bounded fixture replay",
            request_id="round15-complete-fixture-metric",
        )

    assert counter.increments == [("FIXTURE_REPLAY", "succeeded")]
    assert count_gauge.samples == [
        (("FIXTURE_REPLAY", "succeeded", "document_raw"), 3),
        (("FIXTURE_REPLAY", "succeeded", "ready_document_raw"), 2),
        (("FIXTURE_REPLAY", "succeeded", "parse_failed_document_raw"), 0),
        (("FIXTURE_REPLAY", "succeeded", "security_failed_total"), 1),
        (("FIXTURE_REPLAY", "succeeded", "rejected_raw_attempt"), 1),
    ]
    assert ratio_gauge.samples == [
        (("FIXTURE_REPLAY", "succeeded"), 6667)
    ]
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "source_governance_action"
    )
    assert record.event_name == "source_trial_completed"  # type: ignore[attr-defined]
    assert record.outcome == "SUCCEEDED"  # type: ignore[attr-defined]
    assert record.reason_code == "TRIAL_SUCCEEDED"  # type: ignore[attr-defined]
    assert record.source_id == str(SOURCE_ID)  # type: ignore[attr-defined]
    assert record.object_id == str(trial_id)  # type: ignore[attr-defined]
    assert record.trial_kind == "FIXTURE_REPLAY"  # type: ignore[attr-defined]
    assert record.ready_ratio_bps == 6667  # type: ignore[attr-defined]
    assert "complete the bounded fixture replay" not in record.getMessage()


class ConfigRepository:
    async def get_source(self, source_id: UUID) -> SourceRow:
        return _source(SourceLifecycleState.COMPLIANCE_REVIEW)

    async def connector_definition(
        self, connector_type: ConnectorType, definition_version: str
    ) -> ConnectorDefinitionView:
        definition = CONNECTOR_DEFINITIONS[ConnectorKind.RSS_ATOM]
        return ConnectorDefinitionView(
            id=UUID("019b1500-0000-7000-8000-000000000205"),
            connector_type=connector_type,
            definition_version=definition_version,
            schema_version=definition.schema_version,
            schema_document=definition.schema,
            schema_sha256=definition.schema_sha256,
            executor_key=definition.executor_key,
            capabilities=list(definition.capabilities),
        )

    async def current_policy_allowed_hosts(
        self, source_id: UUID, *, now: datetime
    ) -> tuple[str, ...]:
        return ("example.test",)


@pytest.mark.asyncio
async def test_rejected_connector_save_emits_bounded_validation_metric(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    counter = SpyCounter()
    monkeypatch.setattr(service_module, "CONNECTOR_CONFIG_VERSIONS", counter)
    service = SourceRegistryService(ConfigRepository(), DummyVault())  # type: ignore[arg-type]
    payload = ConnectorConfigRequest(
        connector_type=ConnectorType.RSS_ATOM,
        definition_version="1.0.0",
        config={
            "allowed_hosts": ["example.test"],
            "feed_url": "https://example.test/feed",
            "script": "python -c pass",
        },
        reason="reject executable connector content",
    )

    with caplog.at_level(logging.WARNING, logger="srbg.source_registry"):
        with pytest.raises(SourceServiceRejected):
            await service.save_connector_config(
                SOURCE_ID, payload, actor_id=ACTOR_ID, request_id="round15-config-metric"
            )

    assert counter.increments == [("RSS_ATOM", "rejected")]
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "source_governance_action"
    )
    assert record.event_name == "connector_config_version"  # type: ignore[attr-defined]
    assert record.outcome == "REJECTED"  # type: ignore[attr-defined]
    assert record.reason_code == "CONFIG_VALIDATION_REJECTED"  # type: ignore[attr-defined]
    assert record.connector_type == "RSS_ATOM"  # type: ignore[attr-defined]
    assert "python -c pass" not in record.getMessage()


class PolicyRepository:
    async def decide_policy_version(self, *args: object, **kwargs: object) -> UUID:
        return UUID("019b1500-0000-7000-8000-000000000206")

    async def list_policy_versions(self, source_id: UUID) -> list[SourcePolicyVersionView]:
        return [
            SourcePolicyVersionView(
                id=UUID("019b1500-0000-7000-8000-000000000207"),
                source_id=source_id,
                schema_version="2.0.0",
                policy_version="metric-v1",
                status="REJECTED",
                valid_from=datetime.now(UTC),
                valid_until=datetime.now(UTC) + timedelta(days=1),
                document_sha256="a" * 64,
                document={"automatic_publication": "DISABLED"},
                submitted_by=ACTOR_ID,
                decided_by=ACTOR_ID,
                created_at=datetime.now(UTC),
            )
        ]


@pytest.mark.asyncio
async def test_reviewer_policy_rejection_emits_bounded_metric(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    counter = SpyCounter()
    monkeypatch.setattr(service_module, "SOURCE_POLICY_REJECTIONS", counter)
    service = SourceRegistryService(PolicyRepository(), DummyVault())  # type: ignore[arg-type]
    policy_id = UUID("019b1500-0000-7000-8000-000000000207")

    with caplog.at_level(logging.WARNING, logger="srbg.source_registry"):
        await service.decide_policy_version(
            SOURCE_ID,
            policy_id,
            SourcePolicyDecisionRequest(
                outcome=SourcePolicyDecisionOutcome.REJECTED,
                reason="review evidence is not sufficient",
            ),
            actor_id=ACTOR_ID,
            request_id="round15-policy-metric",
        )

    assert counter.increments == [("REVIEWER_REJECTED",)]
    record = next(
        record
        for record in caplog.records
        if record.getMessage() == "source_governance_action"
    )
    assert record.event_name == "source_policy_decision"  # type: ignore[attr-defined]
    assert record.action == "REVIEW_POLICY"  # type: ignore[attr-defined]
    assert record.outcome == "REJECTED"  # type: ignore[attr-defined]
    assert record.reason_code == "REVIEWER_REJECTED"  # type: ignore[attr-defined]
    assert record.source_id == str(SOURCE_ID)  # type: ignore[attr-defined]
    assert record.object_id == str(policy_id)  # type: ignore[attr-defined]
    assert "review evidence is not sufficient" not in record.getMessage()
