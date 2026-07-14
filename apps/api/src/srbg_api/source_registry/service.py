"""Single application service for source admission and raw-document registration."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from srbg_contracts import (
    AuthorityLevel,
    CreateSourceRequest,
    DocumentDetail,
    FixtureUploadResponse,
    SourceChannel,
    SourceDetail,
    SourceEligibility,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceState,
    SourceSummary,
    SourceTransitionRequest,
    SourceType,
)

from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.service import DocumentVaultService, SourceVaultMetrics
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.source_registry.admission import (
    REQUIRED_ONBOARDING_CHECKS,
    AdmissionRejected,
    build_onboarding_record,
    build_policy_record,
)
from srbg_api.source_registry.domain import (
    GateEvidence,
    InvalidSourceTransition,
    SourceGate,
    transition_source,
)
from srbg_api.source_registry.repository import (
    OnboardingRow,
    PolicyRow,
    SourceRow,
    SourceVaultRepository,
    canonical_json_hash,
    fixture_set_hash,
)


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
        return [await self._summary(row) for row in rows]

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
        return await self._detail(row)

    async def get_source(self, source_id: UUID) -> SourceDetail:
        return await self._detail(await self._repository.get_source(source_id))

    async def get_eligibility(self, source_id: UUID) -> SourceEligibility:
        source = await self._repository.get_source(source_id)
        gate, fixture_hashes = await self._gate(source.id)
        return _eligibility(source, gate, fixture_hashes)

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
        gate, fixture_hashes = await self._gate(source.id)
        effective_active = GateEvidence(
            state=source.state,
            enabled=source.enabled,
            gate=gate,
        ).is_effectively_active()
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
            effective_active=effective_active,
            fixture_count=len(set(fixture_hashes)),
            created_at=source.created_at,
        )

    async def _detail(self, source: SourceRow) -> SourceDetail:
        summary = await self._summary(source)
        gate, fixture_hashes = await self._gate(source.id)
        return SourceDetail(
            **summary.model_dump(),
            collection_method=source.collection_method,
            poll_interval_minutes=source.poll_interval_minutes,
            owner=source.owner,
            eligibility=_eligibility(source, gate, fixture_hashes),
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
    )
    return SourceRegistryService(repository, vault)


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
