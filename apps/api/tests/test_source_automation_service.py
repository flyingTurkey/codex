from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import srbg_api.source_automation.service as service_module
from pydantic import ValidationError
from srbg_api.source_automation.repository import (
    ActivationRecord,
    AttentionSlice,
    CandidateSlice,
    StreamSlice,
)
from srbg_api.source_automation.service import (
    SourceAutomationService,
    SourceAutomationServiceRejected,
)
from srbg_contracts import (
    DiscoveryChannel,
    EvidenceCapturePolicy,
    QualificationBundleView,
    QualificationRunStatus,
    QualificationRunView,
    QualificationVerdict,
    SourceCandidateAction,
    SourceCandidateBatchDecisionRequest,
    SourceCandidateBatchTarget,
    SourceCandidateCreateRequest,
    SourceCandidateDecision,
    SourceCandidateDecisionRequest,
    SourceCandidateDetail,
    SourceCandidateQualificationRequest,
    SourceCandidateStatus,
    SourceStreamStatus,
    SourceStreamView,
    StoragePolicy,
)

CANDIDATE_ID = UUID("019b1800-0000-7000-8000-000000000001")
SECOND_ID = UUID("019b1800-0000-7000-8000-000000000002")
SOURCE_ID = UUID("019b1800-0000-7000-8000-000000000003")
NOW = datetime(2026, 7, 17, tzinfo=UTC)


class SpyMetric:
    def __init__(self) -> None:
        self.increments: list[tuple[str, ...]] = []
        self.samples: list[tuple[tuple[str, ...], float]] = []
        self._labels: tuple[str, ...] = ()

    def labels(self, *labels: str) -> "SpyMetric":
        child = SpyMetric()
        child.increments = self.increments
        child.samples = self.samples
        child._labels = tuple(labels)
        return child

    def inc(self) -> None:
        self.increments.append(self._labels)

    def set(self, value: float) -> None:
        self.samples.append((self._labels, value))


def _candidate(
    candidate_id: UUID = CANDIDATE_ID,
    *,
    verdict: QualificationVerdict = QualificationVerdict.QUALIFIED,
    rule_version: str = "source-qualification-v1",
) -> SourceCandidateDetail:
    bundle = QualificationBundleView(
        id=UUID(int=candidate_id.int + 100),
        candidate_id=candidate_id,
        run_id=UUID(int=candidate_id.int + 200),
        rule_version=rule_version,
        material_fingerprint="a" * 64,
        verdict=verdict,
        storage_policy=(
            StoragePolicy.RAW_EVIDENCE_ALLOWED
            if verdict is QualificationVerdict.QUALIFIED
            else StoragePolicy.METADATA_ONLY
        ),
        evidence_capture_policy=EvidenceCapturePolicy.PRIVATE_RAW_ALLOWED,
        checks=[],
        sampled_item_count=5,
        relevant_item_count=5,
        reason_codes=[] if verdict is QualificationVerdict.QUALIFIED else ["TERMS_NOT_PRESENT"],
        bundle_sha256=("b" if candidate_id == CANDIDATE_ID else "c") * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )
    return SourceCandidateDetail(
        id=candidate_id,
        institution_name="Example",
        canonical_url="https://example.gov.cn/engineering/",
        authorization_boundary="example.gov.cn",
        discovery_channels=[DiscoveryChannel.MANUAL],
        status=SourceCandidateStatus.READY_FOR_DECISION,
        occurrence_count=1,
        first_discovered_at=NOW,
        last_discovered_at=NOW,
        latest_qualification=bundle,
        available_actions=[SourceCandidateAction.ENABLE, SourceCandidateAction.DISMISS],
        batch_enable_eligible=verdict is QualificationVerdict.QUALIFIED,
    )


class FakeRepository:
    def __init__(self, candidates: list[SourceCandidateDetail]) -> None:
        self.candidates = {candidate.id: candidate for candidate in candidates}
        self.activations: list[tuple[UUID, str, str]] = []
        self.qualification_requests: list[tuple[UUID, str]] = []

    async def register_manual_candidate(
        self,
        payload: SourceCandidateCreateRequest,
        *,
        canonical_url: str,
        canonical_url_sha256: str,
        authorization_boundary: str,
        material_fingerprint: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        del (
            payload,
            canonical_url,
            canonical_url_sha256,
            authorization_boundary,
            material_fingerprint,
            actor_id,
            request_id,
            now,
        )
        raise AssertionError("registration is not expected")

    async def request_qualification(
        self,
        candidate_id: UUID,
        *,
        rule_version: str,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> QualificationRunView:
        del request_id
        self.qualification_requests.append((candidate_id, reason))
        return QualificationRunView(
            id=UUID(int=candidate_id.int + 500),
            candidate_id=candidate_id,
            status=QualificationRunStatus.PENDING,
            rule_version=rule_version,
            requested_by=actor_id,
            created_at=now,
        )

    async def get_candidate(self, candidate_id: UUID) -> SourceCandidateDetail:
        return self.candidates[candidate_id]

    async def activate_candidate(self, candidate_id: UUID, **kwargs: object) -> ActivationRecord:
        decision = str(kwargs["decision"])
        key = str(kwargs["idempotency_key"])
        self.activations.append((candidate_id, decision, key))
        return ActivationRecord(
            decision_id=UUID(int=candidate_id.int + 300),
            source_id=SOURCE_ID,
            outbox_id=UUID(int=candidate_id.int + 400),
            candidate_status=SourceCandidateStatus.ENABLED,
            idempotent_replay=False,
        )

    async def list_candidates(self, **_: object) -> CandidateSlice:
        return CandidateSlice(items=list(self.candidates.values()), status_counts={})

    async def list_streams(self, **_: object) -> StreamSlice:
        return StreamSlice(items=[])

    async def list_attention(self, **_: object) -> AttentionSlice:
        return AttentionSlice(items=[])

    async def close(self) -> None:
        return None


def _stream(stream_id: UUID, *, updated_at: datetime) -> SourceStreamView:
    return SourceStreamView(
        id=stream_id,
        source_id=SOURCE_ID,
        candidate_id=CANDIDATE_ID,
        institution_name="Example",
        canonical_url="https://example.gov.cn/engineering/",
        authorization_boundary="example.gov.cn",
        stream_key=str(stream_id),
        status=SourceStreamStatus.ACTIVE,
        rule_version="source-qualification-v1",
        updated_at=updated_at,
    )


@pytest.mark.asyncio
async def test_individual_warning_cannot_be_enabled_without_explicit_waiver() -> None:
    repository = FakeRepository([_candidate(verdict=QualificationVerdict.WARN_WAIVABLE)])
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    with pytest.raises(SourceAutomationServiceRejected, match="waiver"):
        await service.decide_candidate(
            CANDIDATE_ID,
            SourceCandidateDecisionRequest(
                decision=SourceCandidateDecision.ENABLE,
                expected_bundle_sha256="b" * 64,
                reason="enable restricted source",
            ),
            actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
            request_id="request-1",
            idempotency_key="decision-key-1",
        )

    assert repository.activations == []


def test_enable_requires_the_bundle_hash_the_administrator_reviewed() -> None:
    repository = FakeRepository([_candidate()])

    with pytest.raises(ValidationError, match="bundle SHA-256"):
        SourceCandidateDecisionRequest(
            decision=SourceCandidateDecision.ENABLE,
            reason=(
                "enable only the qualification package reviewed by the administrator"
            ),
        )

    assert repository.activations == []


@pytest.mark.asyncio
async def test_failed_candidate_without_bundle_can_be_dismissed_but_not_enabled() -> None:
    candidate = _candidate().model_copy(
        update={
            "status": SourceCandidateStatus.BLOCKED,
            "latest_qualification": None,
            "available_actions": [
                SourceCandidateAction.REQUEST_QUALIFICATION,
                SourceCandidateAction.DISMISS,
            ],
            "batch_enable_eligible": False,
        }
    )

    class DismissRepository(FakeRepository):
        received_bundle_hash: str | None = "not-called"

        async def activate_candidate(
            self,
            candidate_id: UUID,
            **kwargs: object,
        ) -> ActivationRecord:
            assert kwargs["decision"] == "DISMISS"
            value = kwargs["expected_bundle_sha256"]
            assert value is None or isinstance(value, str)
            self.received_bundle_hash = value
            return ActivationRecord(
                decision_id=UUID(int=candidate_id.int + 300),
                source_id=None,
                outbox_id=None,
                candidate_status=SourceCandidateStatus.DISMISSED,
                idempotent_replay=False,
            )

    repository = DismissRepository([candidate])
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    result = await service.decide_candidate(
        CANDIDATE_ID,
        SourceCandidateDecisionRequest(
            decision=SourceCandidateDecision.DISMISS,
            reason="dismiss failed source candidate",
        ),
        actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
        request_id="request-dismiss-failed",
        idempotency_key="decision-dismiss-failed",
    )

    assert result.status is SourceCandidateStatus.DISMISSED
    assert repository.received_bundle_hash is None


@pytest.mark.asyncio
async def test_batch_preflight_rejects_mixed_rule_versions_before_any_item_transaction() -> None:
    repository = FakeRepository(
        [
            _candidate(),
            _candidate(SECOND_ID, rule_version="source-qualification-v2"),
        ]
    )
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    with pytest.raises(SourceAutomationServiceRejected, match="rule version"):
        await service.decide_candidate_batch(
            SourceCandidateBatchDecisionRequest(
                targets=[
                    SourceCandidateBatchTarget(
                        candidate_id=CANDIDATE_ID,
                        expected_bundle_sha256="b" * 64,
                    ),
                    SourceCandidateBatchTarget(
                        candidate_id=SECOND_ID,
                        expected_bundle_sha256="c" * 64,
                    ),
                ],
                expected_rule_version="source-qualification-v1",
                reason="enable same-rule green cohort",
            ),
            actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
            request_id="request-2",
            idempotency_key="batch-key-1",
        )

    assert repository.activations == []


@pytest.mark.asyncio
async def test_stream_cursor_uses_the_same_updated_at_order_as_the_repository() -> None:
    class StreamRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__([])
            self.after_values: list[tuple[datetime, UUID] | None] = []

        async def list_streams(self, **kwargs: object) -> StreamSlice:
            after = kwargs.get("after")
            assert after is None or isinstance(after, tuple)
            self.after_values.append(after)
            if after is not None:
                return StreamSlice(items=[])
            return StreamSlice(
                items=[
                    _stream(CANDIDATE_ID, updated_at=NOW),
                    _stream(SECOND_ID, updated_at=NOW - timedelta(minutes=1)),
                ]
            )

    repository = StreamRepository()
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    first = await service.list_streams(limit=1, cursor=None, query=None)
    assert first.next_cursor is not None
    await service.list_streams(limit=1, cursor=first.next_cursor, query=None)

    assert repository.after_values == [None, (NOW, CANDIDATE_ID)]


@pytest.mark.asyncio
async def test_manual_discovery_automatically_enters_initial_qualification() -> None:
    class RegistrationRepository(FakeRepository):
        def __init__(self) -> None:
            super().__init__([
                _candidate().model_copy(
                    update={
                        "status": SourceCandidateStatus.DISCOVERED,
                        "latest_qualification": None,
                    }
                )
            ])
        async def register_manual_candidate(
            self,
            payload: SourceCandidateCreateRequest,
            *,
            canonical_url: str,
            canonical_url_sha256: str,
            authorization_boundary: str,
            material_fingerprint: str,
            actor_id: UUID,
            request_id: str,
            now: datetime,
        ) -> UUID:
            del (
                payload,
                canonical_url,
                canonical_url_sha256,
                authorization_boundary,
                material_fingerprint,
                actor_id,
                request_id,
                now,
            )
            return CANDIDATE_ID

    repository = RegistrationRepository()
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    result = await service.create_candidate(
        SourceCandidateCreateRequest(
            url="https://example.gov.cn/engineering/",
            reason="submit public engineering source",
        ),
        actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
        request_id="request-auto-qualification",
    )

    assert result.id == CANDIDATE_ID
    assert repository.qualification_requests == [
        (CANDIDATE_ID, "automatic initial qualification after manual discovery")
    ]


@pytest.mark.asyncio
async def test_manual_candidate_rejects_an_invalid_port_as_validation_not_server_error() -> None:
    service = SourceAutomationService(
        FakeRepository([]),
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    with pytest.raises(SourceAutomationServiceRejected) as error:
        await service.create_candidate(
            SourceCandidateCreateRequest(
                url="https://example.gov.cn:not-a-port/engineering/",
                reason="reject malformed public engineering source URL",
            ),
            actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
            request_id="request-invalid-port",
        )

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_automation_metrics_use_only_bounded_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MetricsRepository(FakeRepository):
        async def list_candidates(self, **_: object) -> CandidateSlice:
            return CandidateSlice(
                items=list(self.candidates.values()),
                status_counts={SourceCandidateStatus.READY_FOR_DECISION: 1},
            )

    qualification_metric = SpyMetric()
    decision_metric = SpyMetric()
    backlog_metric = SpyMetric()
    monkeypatch.setattr(
        service_module,
        "SOURCE_AUTOMATION_QUALIFICATION_REQUESTS",
        qualification_metric,
    )
    monkeypatch.setattr(
        service_module,
        "SOURCE_AUTOMATION_CANDIDATE_DECISIONS",
        decision_metric,
    )
    monkeypatch.setattr(
        service_module,
        "SOURCE_AUTOMATION_CANDIDATE_BACKLOG",
        backlog_metric,
    )
    repository = MetricsRepository([_candidate()])
    service = SourceAutomationService(
        repository,
        cursor_signing_key=b"x" * 48,
        now=lambda: NOW,
    )

    await service.list_candidates(
        limit=20,
        cursor=None,
        status=None,
        verdict=None,
        discovery_channel=None,
        industry=None,
        content_domain=None,
        language_tag=None,
        query=None,
    )
    await service.request_qualification(
        CANDIDATE_ID,
        SourceCandidateQualificationRequest(reason="repeat current qualification"),
        actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
        request_id="request-metrics-qualification",
    )
    await service.decide_candidate(
        CANDIDATE_ID,
        SourceCandidateDecisionRequest(
            decision=SourceCandidateDecision.ENABLE,
            expected_bundle_sha256="b" * 64,
            reason="enable current qualified candidate",
        ),
        actor_id=UUID("019b1800-0000-7000-8000-000000000090"),
        request_id="request-metrics-decision",
        idempotency_key="metrics-decision-key",
    )

    assert qualification_metric.increments == [("operator", "ENQUEUED")]
    assert decision_metric.increments == [("ENABLE", "APPLIED")]
    assert (
        (SourceCandidateStatus.READY_FOR_DECISION.value,),
        1.0,
    ) in backlog_metric.samples
    assert all(len(labels) == 1 for labels, _ in backlog_metric.samples)
