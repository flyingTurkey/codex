"""Application service for the automated source lifecycle."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from srbg_contracts import (
    DiscoveryChannel,
    QualificationBundleView,
    QualificationRunView,
    QualificationVerdict,
    SourceAttentionPage,
    SourceCandidateBatchDecisionRequest,
    SourceCandidateBatchDecisionResult,
    SourceCandidateCreateRequest,
    SourceCandidateDecision,
    SourceCandidateDecisionItemOutcome,
    SourceCandidateDecisionItemResult,
    SourceCandidateDecisionRequest,
    SourceCandidateDecisionResult,
    SourceCandidateDetail,
    SourceCandidatePage,
    SourceCandidateQualificationRequest,
    SourceCandidateStatus,
    SourceContentDomain,
    SourceIndustry,
    SourceStreamPage,
)

from srbg_api.database import create_database_engine
from srbg_api.discovery.domain import CursorCodec
from srbg_api.observability import (
    SOURCE_AUTOMATION_CANDIDATE_BACKLOG,
    SOURCE_AUTOMATION_CANDIDATE_DECISIONS,
    SOURCE_AUTOMATION_QUALIFICATION_REQUESTS,
)
from srbg_api.source_automation.domain import (
    AutomationRuleViolation,
    QualificationAssessment,
    authorize_candidate_decision,
    validate_batch_enable,
)
from srbg_api.source_automation.repository import (
    ActivationRecord,
    AttentionSlice,
    CandidateSlice,
    PostgresSourceAutomationRepository,
    SourceAutomationConflict,
    SourceAutomationNotFound,
    StreamSlice,
)

SOURCE_QUALIFICATION_RULE_VERSION = "source-qualification-v1"


class AutomationRepository(Protocol):
    async def list_candidates(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
        status: SourceCandidateStatus | None,
        verdict: QualificationVerdict | None,
        discovery_channel: DiscoveryChannel | None,
        industry: SourceIndustry | None,
        content_domain: SourceContentDomain | None,
        language_tag: str | None,
        query: str | None,
    ) -> CandidateSlice: ...

    async def get_candidate(self, candidate_id: UUID) -> SourceCandidateDetail: ...

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
    ) -> UUID: ...

    async def request_qualification(
        self,
        candidate_id: UUID,
        *,
        rule_version: str,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> QualificationRunView: ...

    async def activate_candidate(
        self,
        candidate_id: UUID,
        *,
        decision: str,
        expected_bundle_sha256: str | None,
        request_sha256: str,
        idempotency_key: str,
        reason: str,
        waiver_reason: str | None,
        actor_id: UUID,
        now: datetime,
    ) -> ActivationRecord: ...

    async def list_streams(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
        query: str | None,
    ) -> StreamSlice: ...

    async def list_attention(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
    ) -> AttentionSlice: ...

    async def close(self) -> None: ...


class SourceAutomationServiceRejected(RuntimeError):
    def __init__(self, detail: str, status_code: int = 409) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class SourceAutomationService:
    def __init__(
        self,
        repository: AutomationRepository,
        *,
        cursor_signing_key: bytes,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._cursor = CursorCodec(cursor_signing_key)
        self._now = now

    async def close(self) -> None:
        await self._repository.close()

    async def list_candidates(
        self,
        *,
        limit: int,
        cursor: str | None,
        status: SourceCandidateStatus | None,
        verdict: QualificationVerdict | None,
        discovery_channel: DiscoveryChannel | None,
        industry: SourceIndustry | None = None,
        content_domain: SourceContentDomain | None = None,
        language_tag: str | None = None,
        query: str | None,
    ) -> SourceCandidatePage:
        binding: dict[str, object] = {
            "kind": "source-candidates-v1",
            "status": None if status is None else status.value,
            "verdict": None if verdict is None else verdict.value,
            "discovery_channel": (
                None if discovery_channel is None else discovery_channel.value
            ),
            "industry": None if industry is None else industry.value,
            "content_domain": None if content_domain is None else content_domain.value,
            "language_tag": language_tag,
            "query": query,
        }
        after = _decode_cursor(self._cursor, cursor, binding=binding)
        result = await self._repository.list_candidates(
            limit=limit + 1,
            after=after,
            status=status,
            verdict=verdict,
            discovery_channel=discovery_channel,
            industry=industry,
            content_domain=content_domain,
            language_tag=language_tag,
            query=query,
        )
        for candidate_status in SourceCandidateStatus:
            SOURCE_AUTOMATION_CANDIDATE_BACKLOG.labels(candidate_status.value).set(
                float(result.status_counts.get(candidate_status, 0))
            )
        has_more = len(result.items) > limit
        items = result.items[:limit]
        return SourceCandidatePage(
            items=items,
            next_cursor=(
                _encode_cursor(
                    self._cursor,
                    items[-1].last_discovered_at,
                    items[-1].id,
                    binding=binding,
                )
                if has_more and items
                else None
            ),
            has_more=has_more,
            status_counts=result.status_counts,
        )

    async def create_candidate(
        self,
        payload: SourceCandidateCreateRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceCandidateDetail:
        canonical_url, boundary = _normalize_candidate_url(payload.url)
        url_sha256 = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()
        candidate_id = await self._repository.register_manual_candidate(
            payload,
            canonical_url=canonical_url,
            canonical_url_sha256=url_sha256,
            authorization_boundary=boundary,
            material_fingerprint=url_sha256,
            actor_id=actor_id,
            request_id=request_id,
            now=self._now(),
        )
        candidate = await self._repository.get_candidate(candidate_id)
        if candidate.status in {
            SourceCandidateStatus.DISCOVERED,
            SourceCandidateStatus.STALE,
            SourceCandidateStatus.BLOCKED,
        }:
            await self._repository.request_qualification(
                candidate_id,
                rule_version=SOURCE_QUALIFICATION_RULE_VERSION,
                reason="automatic initial qualification after manual discovery",
                actor_id=actor_id,
                request_id=request_id,
                now=self._now(),
            )
            SOURCE_AUTOMATION_QUALIFICATION_REQUESTS.labels(
                "automatic", "ENQUEUED"
            ).inc()
            candidate = await self._repository.get_candidate(candidate_id)
        return candidate

    async def get_candidate(self, candidate_id: UUID) -> SourceCandidateDetail:
        try:
            return await self._repository.get_candidate(candidate_id)
        except SourceAutomationNotFound as exc:
            raise SourceAutomationServiceRejected(str(exc), 404) from exc

    async def request_qualification(
        self,
        candidate_id: UUID,
        payload: SourceCandidateQualificationRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> QualificationRunView:
        try:
            run = await self._repository.request_qualification(
                candidate_id,
                rule_version=SOURCE_QUALIFICATION_RULE_VERSION,
                reason=payload.reason,
                actor_id=actor_id,
                request_id=request_id,
                now=self._now(),
            )
        except (SourceAutomationConflict, SourceAutomationNotFound) as exc:
            SOURCE_AUTOMATION_QUALIFICATION_REQUESTS.labels(
                "operator", "REJECTED"
            ).inc()
            raise SourceAutomationServiceRejected(str(exc)) from exc
        SOURCE_AUTOMATION_QUALIFICATION_REQUESTS.labels("operator", "ENQUEUED").inc()
        return run

    async def decide_candidate(
        self,
        candidate_id: UUID,
        payload: SourceCandidateDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
    ) -> SourceCandidateDecisionResult:
        del request_id
        candidate = await self.get_candidate(candidate_id)
        bundle = candidate.latest_qualification
        if bundle is None and payload.decision is not SourceCandidateDecision.DISMISS:
            SOURCE_AUTOMATION_CANDIDATE_DECISIONS.labels(
                payload.decision.value, "REJECTED"
            ).inc()
            raise SourceAutomationServiceRejected("candidate has no current qualification bundle")
        expected_hash = (
            payload.expected_bundle_sha256
            or (None if bundle is None else bundle.bundle_sha256)
        )
        try:
            if bundle is not None:
                if expected_hash is None:
                    raise AutomationRuleViolation(
                        "qualification bundle hash is required"
                    )
                authorize_candidate_decision(
                    _assessment_from_view(bundle),
                    decision=payload.decision,
                    expected_bundle_sha256=expected_hash,
                    current_material_fingerprint=bundle.material_fingerprint,
                    waiver_reason=payload.waiver_reason,
                    now=self._now(),
                )
            request_sha256 = _decision_request_sha256(candidate_id, payload)
            activation = await self._repository.activate_candidate(
                candidate_id,
                decision=payload.decision.value,
                expected_bundle_sha256=expected_hash,
                request_sha256=request_sha256,
                idempotency_key=idempotency_key,
                reason=payload.reason,
                waiver_reason=payload.waiver_reason,
                actor_id=actor_id,
                now=self._now(),
            )
        except (AutomationRuleViolation, SourceAutomationConflict) as exc:
            SOURCE_AUTOMATION_CANDIDATE_DECISIONS.labels(
                payload.decision.value, "REJECTED"
            ).inc()
            raise SourceAutomationServiceRejected(str(exc)) from exc
        SOURCE_AUTOMATION_CANDIDATE_DECISIONS.labels(
            payload.decision.value,
            "IDEMPOTENT" if activation.idempotent_replay else "APPLIED",
        ).inc()
        return SourceCandidateDecisionResult(
            candidate_id=candidate_id,
            status=activation.candidate_status,
            source_id=activation.source_id,
            production_refetch_enqueued=activation.outbox_id is not None,
            idempotent_replay=activation.idempotent_replay,
            decided_at=self._now(),
        )

    async def decide_candidate_batch(
        self,
        payload: SourceCandidateBatchDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
        idempotency_key: str,
    ) -> SourceCandidateBatchDecisionResult:
        candidates = [
            await self.get_candidate(target.candidate_id) for target in payload.targets
        ]
        assessments: list[QualificationAssessment] = []
        for target, candidate in zip(payload.targets, candidates, strict=True):
            bundle = candidate.latest_qualification
            if bundle is None or bundle.bundle_sha256 != target.expected_bundle_sha256:
                raise SourceAutomationServiceRejected(
                    "batch target qualification bundle is stale"
                )
            assessments.append(_assessment_from_view(bundle))
        try:
            validate_batch_enable(
                assessments,
                expected_rule_version=payload.expected_rule_version,
                now=self._now(),
            )
        except AutomationRuleViolation as exc:
            raise SourceAutomationServiceRejected(str(exc)) from exc

        items: list[SourceCandidateDecisionItemResult] = []
        replay_flags: list[bool] = []
        for target in payload.targets:
            item_key = _batch_item_key(idempotency_key, target.candidate_id)
            try:
                result = await self.decide_candidate(
                    target.candidate_id,
                    SourceCandidateDecisionRequest(
                        decision=SourceCandidateDecision.ENABLE,
                        expected_bundle_sha256=target.expected_bundle_sha256,
                        reason=payload.reason,
                    ),
                    actor_id=actor_id,
                    request_id=request_id,
                    idempotency_key=item_key,
                )
            except SourceAutomationServiceRejected as exc:
                items.append(
                    SourceCandidateDecisionItemResult(
                        candidate_id=target.candidate_id,
                        outcome=SourceCandidateDecisionItemOutcome.CONFLICT,
                        production_refetch_enqueued=False,
                        reason_code=_conflict_reason_code(exc.detail),
                    )
                )
                replay_flags.append(False)
            else:
                items.append(
                    SourceCandidateDecisionItemResult(
                        candidate_id=target.candidate_id,
                        outcome=SourceCandidateDecisionItemOutcome.APPLIED,
                        status=result.status,
                        source_id=result.source_id,
                        production_refetch_enqueued=result.production_refetch_enqueued,
                    )
                )
                replay_flags.append(result.idempotent_replay)
        return SourceCandidateBatchDecisionResult(
            items=items,
            rule_version=payload.expected_rule_version,
            decided_at=self._now(),
            idempotent_replay=bool(replay_flags and all(replay_flags)),
        )

    async def list_streams(
        self,
        *,
        limit: int,
        cursor: str | None,
        query: str | None,
    ) -> SourceStreamPage:
        binding: dict[str, object] = {"kind": "source-streams-v1", "query": query}
        after = _decode_cursor(self._cursor, cursor, binding=binding)
        result = await self._repository.list_streams(
            limit=limit + 1,
            after=after,
            query=query,
        )
        has_more = len(result.items) > limit
        items = result.items[:limit]
        return SourceStreamPage(
            items=items,
            next_cursor=(
                _encode_cursor(
                    self._cursor,
                    items[-1].updated_at,
                    items[-1].id,
                    binding=binding,
                )
                if has_more and items
                else None
            ),
            has_more=has_more,
        )

    async def list_attention(
        self,
        *,
        limit: int,
        cursor: str | None,
    ) -> SourceAttentionPage:
        binding: dict[str, object] = {"kind": "source-attention-v1"}
        after = _decode_cursor(self._cursor, cursor, binding=binding)
        result = await self._repository.list_attention(limit=limit + 1, after=after)
        has_more = len(result.items) > limit
        items = result.items[:limit]
        return SourceAttentionPage(
            items=items,
            next_cursor=(
                _encode_cursor(
                    self._cursor,
                    items[-1].last_observed_at,
                    items[-1].stream.id,
                    binding=binding,
                )
                if has_more and items
                else None
            ),
            has_more=has_more,
        )


def build_default_source_automation_service(settings: object) -> SourceAutomationService:
    from srbg_api.config import Settings

    if not isinstance(settings, Settings):
        raise TypeError("source automation settings are invalid")
    return SourceAutomationService(
        PostgresSourceAutomationRepository(create_database_engine(settings)),
        cursor_signing_key=settings.cursor_signing_key.get_secret_value().encode(),
    )


def _assessment_from_view(bundle: QualificationBundleView) -> QualificationAssessment:
    return QualificationAssessment(
        rule_version=bundle.rule_version,
        material_fingerprint=bundle.material_fingerprint,
        verdict=bundle.verdict,
        storage_policy=bundle.storage_policy,
        evidence_capture_policy=bundle.evidence_capture_policy,
        reason_codes=tuple(bundle.reason_codes),
        sampled_item_count=bundle.sampled_item_count,
        relevant_item_count=bundle.relevant_item_count,
        bundle_sha256=bundle.bundle_sha256,
        created_at=bundle.created_at,
        expires_at=bundle.expires_at,
    )


def _normalize_candidate_url(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise SourceAutomationServiceRejected("candidate URL is invalid", 422) from exc
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise SourceAutomationServiceRejected(
            "candidate URL must be credential-free HTTPS without query or fragment",
            422,
        )
    try:
        host = hostname.encode("idna").decode("ascii").rstrip(".").casefold()
        ipaddress.ip_address(host)
    except UnicodeError as exc:
        raise SourceAutomationServiceRejected("candidate host name is invalid", 422) from exc
    except ValueError:
        pass
    else:
        raise SourceAutomationServiceRejected("candidate host cannot be an IP literal", 422)
    if host == "localhost" or "." not in host:
        raise SourceAutomationServiceRejected("candidate host must be a public DNS name", 422)
    path = parsed.path or "/"
    canonical = urlunsplit(("https", host, path, "", ""))
    return canonical, host


def _decision_request_sha256(
    candidate_id: UUID,
    payload: SourceCandidateDecisionRequest,
) -> str:
    document = {
        "candidate_id": str(candidate_id),
        "payload": payload.model_dump(mode="json", exclude_none=False),
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _batch_item_key(base_key: str, candidate_id: UUID) -> str:
    digest = hashlib.sha256(f"{base_key}:{candidate_id}".encode()).hexdigest()
    return f"batch-{digest}"


def _conflict_reason_code(detail: str) -> str:
    upper = "".join(character if character.isalnum() else "_" for character in detail.upper())
    bounded = "_".join(part for part in upper.split("_") if part)[:100]
    return bounded or "SOURCE_AUTOMATION_CONFLICT"


def _encode_cursor(
    codec: CursorCodec,
    observed_at: datetime,
    item_id: UUID,
    *,
    binding: dict[str, object],
) -> str:
    return codec.encode(
        sort_values=(observed_at.astimezone(UTC).isoformat(), str(item_id)),
        binding=binding,
    )


def _decode_cursor(
    codec: CursorCodec,
    cursor: str | None,
    *,
    binding: dict[str, object],
) -> tuple[datetime, UUID] | None:
    if cursor is None:
        return None
    values = codec.decode(cursor, binding=binding)
    if len(values) != 2:
        from srbg_api.discovery.domain import CursorBindingError

        raise CursorBindingError("source workspace cursor shape is invalid")
    try:
        observed_at = datetime.fromisoformat(values[0])
        item_id = UUID(values[1])
    except ValueError as exc:
        from srbg_api.discovery.domain import CursorBindingError

        raise CursorBindingError("source workspace cursor values are invalid") from exc
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        from srbg_api.discovery.domain import CursorBindingError

        raise CursorBindingError("source workspace cursor timestamp is invalid")
    return observed_at.astimezone(UTC), item_id
