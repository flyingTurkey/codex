"""Isolated source qualification and production-refetch activation workers.

Paid-search material is intentionally transient.  A provider hit can only be
handed to the target probe in this process; persistence accepts the typed,
post-probe target evidence below and has no provider-payload entry point.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.contracts import FetchResult, SourceCheckpoint
from srbg_api.acquisition.http import (
    Clock,
    FetchPolicy,
    HttpResponse,
    ResilientHttpClient,
    Resolver,
    SsrfRejected,
)
from srbg_api.acquisition.live import HttpxTransport, SystemClock, SystemResolver
from srbg_api.config import Settings
from srbg_api.connectors.parsers import DeclarativeParseError, ListDetailConnector
from srbg_api.database import create_database_engine
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.security import MalwareDetected, MalwareScanInconclusive
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.source_automation.domain import QualificationFacts, evaluate_qualification
from srbg_contracts import ReviewEvidenceResult as EvidenceReview

MAX_TARGET_BYTES = 50 * 1024 * 1024


class QualificationExecutionError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = _reason_code(reason_code)
        super().__init__(self.reason_code)


class ProviderDisabled(QualificationExecutionError):
    def __init__(self) -> None:
        super().__init__("PROVIDER_DISABLED")


class QualificationPolicyBlocked(QualificationExecutionError):
    def __init__(self, reason_code: str, *, evidence_fingerprint: str) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", evidence_fingerprint) is None:
            raise ValueError("policy evidence fingerprint is invalid")
        self.evidence_fingerprint = evidence_fingerprint
        super().__init__(reason_code)


@dataclass(frozen=True, slots=True)
class ProviderHit:
    """Ephemeral provider material; this type is never accepted by a gateway."""

    url: str
    title: str | None = None
    snippet: str | None = None

    def __post_init__(self) -> None:
        if not _is_https_url(self.url) or len(self.url) > 2048:
            raise ValueError("provider target URL must be bounded HTTPS")
        if self.title is not None and len(self.title) > 1000:
            raise ValueError("provider title is too long")
        if self.snippet is not None and len(self.snippet) > 4000:
            raise ValueError("provider snippet is too long")


@dataclass(frozen=True, slots=True)
class SafeTargetCapture:
    requested_url: str
    final_url: str
    content: bytes
    content_type: str
    status_code: int
    response_sha256: str
    captured_at: datetime

    def __post_init__(self) -> None:
        if not _is_https_url(self.requested_url) or not _is_https_url(self.final_url):
            raise ValueError("qualification capture URLs must be HTTPS")
        if not 100 <= self.status_code <= 599:
            raise ValueError("qualification HTTP status is invalid")
        if not 0 < len(self.content) <= MAX_TARGET_BYTES:
            raise ValueError("qualification target body is empty or too large")
        if not 1 <= len(self.content_type) <= 100:
            raise ValueError("qualification content type is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.response_sha256) is None:
            raise ValueError("qualification response hash is invalid")
        if self.captured_at.tzinfo is None:
            raise ValueError("qualification capture time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SafeTargetEvidence:
    capture: SafeTargetCapture
    resolved_addresses_public: bool
    redirect_boundary_valid: bool
    robots: EvidenceReview
    terms: EvidenceReview
    copyright: EvidenceReview
    requires_login: bool
    captcha_detected: bool
    paywall_detected: bool
    connector_valid: bool
    relevant: bool
    raw_evidence_storage_prohibited: bool = False


@dataclass(frozen=True, slots=True)
class QualificationBinding:
    qualification_run_id: UUID
    candidate_id: UUID
    campaign_id: UUID | None
    canonical_url: str
    authorization_boundary: str
    rule_version: str
    material_fingerprint: str
    lease_token: UUID
    prepared_source_id: UUID | None = None
    prepared_policy_version_id: UUID | None = None
    prepared_connector_config_version_id: UUID | None = None
    prepared_trial_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if not _is_https_url(self.canonical_url):
            raise ValueError("qualification canonical URL must be HTTPS")
        if not _valid_boundary(self.authorization_boundary):
            raise ValueError("qualification authorization boundary is invalid")
        if not 1 <= len(self.rule_version) <= 80:
            raise ValueError("qualification rule version is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.material_fingerprint) is None:
            raise ValueError("qualification material fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class QualificationCheck:
    code: str
    outcome: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Z0-9_]{1,80}", self.code) is None:
            raise ValueError("qualification check code is invalid")
        if self.outcome not in {"PASS", "WARN", "BLOCK"}:
            raise ValueError("qualification check outcome is invalid")


@dataclass(frozen=True, slots=True)
class QualificationSummary:
    material_fingerprint: str
    evidence_fingerprint: str
    verdict: str
    storage_policy: str
    evidence_capture_policy: str
    checks: tuple[QualificationCheck, ...]
    reason_codes: tuple[str, ...]
    sampled_item_count: int
    relevant_item_count: int
    bundle_sha256: str
    created_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.material_fingerprint) is None:
            raise ValueError("qualification material fingerprint is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.evidence_fingerprint) is None:
            raise ValueError("qualification evidence fingerprint is invalid")
        if self.verdict not in {"QUALIFIED", "WARN_WAIVABLE", "BLOCKED"}:
            raise ValueError("qualification verdict is invalid")
        if self.storage_policy not in {
            "RAW_EVIDENCE_ALLOWED",
            "METADATA_ONLY",
            "LINK_ONLY",
        }:
            raise ValueError("qualification storage policy is invalid")
        if self.evidence_capture_policy not in {
            "PRIVATE_RAW_ALLOWED",
            "TRANSIENT_METADATA_ONLY",
        }:
            raise ValueError("qualification evidence capture policy is invalid")
        if not 0 <= self.relevant_item_count <= self.sampled_item_count:
            raise ValueError("qualification sample counts are invalid")
        if any(re.fullmatch(r"[A-Z0-9_]{1,100}", code) is None for code in self.reason_codes):
            raise ValueError("qualification reason code is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.bundle_sha256) is None:
            raise ValueError("qualification bundle hash is invalid")
        if (
            self.created_at.tzinfo is None
            or self.valid_until.tzinfo is None
            or self.valid_until <= self.created_at
        ):
            raise ValueError("qualification validity window is invalid")


@dataclass(frozen=True, slots=True)
class QualificationOutcome:
    qualification_run_id: UUID
    acquired: bool
    status: str
    target_evidence_count: int


@dataclass(frozen=True, slots=True)
class ActivationDispatch:
    outbox_id: UUID
    source_id: UUID
    fetch_run_id: UUID
    needs_dispatch: bool


@dataclass(frozen=True, slots=True)
class ActivationOutcome:
    outbox_id: UUID
    source_id: UUID | None
    fetch_run_id: UUID | None
    status: str
    dispatched: bool


class SearchProvider(Protocol):
    async def discover_targets(
        self,
        binding: QualificationBinding,
    ) -> tuple[ProviderHit, ...]: ...


class TargetProbe(Protocol):
    async def probe(
        self,
        url: str,
        *,
        authorization_boundary: str,
    ) -> SafeTargetEvidence: ...


class QualificationGateway(Protocol):
    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]: ...

    async def acquire(
        self,
        qualification_run_id: UUID,
    ) -> QualificationBinding | None: ...

    async def record_target_evidence(
        self,
        binding: QualificationBinding,
        evidence: SafeTargetEvidence,
    ) -> UUID: ...

    async def complete(
        self,
        binding: QualificationBinding,
        summary: QualificationSummary,
    ) -> str: ...

    async def fail(self, binding: QualificationBinding, *, reason_code: str) -> str: ...

    async def close(self) -> None: ...


class ActivationOutboxGateway(Protocol):
    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]: ...

    async def prepare(self, outbox_id: UUID) -> ActivationDispatch | None: ...

    async def mark_succeeded(self, dispatch: ActivationDispatch) -> bool: ...

    async def close(self) -> None: ...


class DisabledSearchProvider:
    async def discover_targets(
        self,
        binding: QualificationBinding,
    ) -> tuple[ProviderHit, ...]:
        del binding
        raise ProviderDisabled


class CanonicalTargetProvider:
    """Create one transient target from the authoritative candidate URL."""

    async def discover_targets(
        self,
        binding: QualificationBinding,
    ) -> tuple[ProviderHit, ...]:
        return (ProviderHit(url=binding.canonical_url),)


class DisabledTargetProbe:
    async def probe(
        self,
        url: str,
        *,
        authorization_boundary: str,
    ) -> SafeTargetEvidence:
        del url, authorization_boundary
        raise QualificationExecutionError("TARGET_PROBE_DISABLED")


class _ClosableTransport(Protocol):
    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse: ...

    async def close(self) -> None: ...


class ResilientTargetProbe:
    """Fetch a candidate target through the shared DNS-pinned HTTP boundary."""

    def __init__(
        self,
        settings: Settings,
        *,
        resolver: Resolver | None = None,
        transport_factory: Callable[[], _ClosableTransport] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._settings = settings
        self._resolver = resolver or SystemResolver()
        self._transport_factory = transport_factory or HttpxTransport
        self._clock = clock or SystemClock()

    async def probe(
        self,
        url: str,
        *,
        authorization_boundary: str,
    ) -> SafeTargetEvidence:
        if _authorized_target_key(url, authorization_boundary=authorization_boundary) is None:
            raise QualificationExecutionError("TARGET_OUTSIDE_AUTHORIZATION_BOUNDARY")
        robots = await self._review_robots(
            url,
            authorization_boundary=authorization_boundary,
        )
        policy = FetchPolicy(
            allowed_hosts=(authorization_boundary,),
            timeout_seconds=self._settings.external_io_timeout_seconds,
            max_attempts=1,
            base_backoff_seconds=0.0,
            rate_limit_per_minute=6,
            minimum_interval_seconds=1,
            circuit_failure_threshold=1,
            circuit_reset_seconds=60.0,
            max_redirects=3,
            user_agent="SRBGQualificationProbe/1.0",
            max_response_bytes=min(MAX_TARGET_BYTES, self._settings.fixture_max_bytes),
        )
        transport = self._transport_factory()
        client = ResilientHttpClient(
            policy,
            resolver=self._resolver,
            transport=transport,
            clock=self._clock,
        )
        try:
            result = await client.get(
                url,
                checkpoint=SourceCheckpoint(),
                accept="text/html,application/xhtml+xml,application/pdf",
            )
        except SsrfRejected as error:
            raise QualificationExecutionError("TARGET_SSRF_REJECTED") from error
        except (OSError, ValueError) as error:
            raise QualificationExecutionError("TARGET_FETCH_FAILED") from error
        finally:
            await transport.close()

        content = result.content
        if not content:
            raise QualificationExecutionError("TARGET_EMPTY_RESPONSE")
        response_sha256 = result.response_sha256 or sha256(content).hexdigest()
        requires_login, captcha_detected, paywall_detected = _target_access_signals(content)
        return SafeTargetEvidence(
            capture=SafeTargetCapture(
                requested_url=url,
                final_url=result.url,
                content=content,
                content_type=_bounded_content_type(
                    result.content_type or "application/octet-stream"
                ),
                status_code=result.status_code,
                response_sha256=response_sha256,
                captured_at=result.fetched_at,
            ),
            resolved_addresses_public=True,
            redirect_boundary_valid=(
                _authorized_target_key(
                    result.url,
                    authorization_boundary=authorization_boundary,
                )
                is not None
            ),
            robots=robots,
            terms=EvidenceReview.NOT_PRESENT,
            copyright=EvidenceReview.NOT_PRESENT,
            requires_login=requires_login,
            captcha_detected=captcha_detected,
            paywall_detected=paywall_detected,
            connector_valid=_generic_connector_valid(result, authorization_boundary),
            relevant=_target_is_engineering_relevant(result.url, content),
        )

    async def _review_robots(
        self,
        target_url: str,
        *,
        authorization_boundary: str,
    ) -> EvidenceReview:
        robots_url = f"https://{authorization_boundary}/robots.txt"
        transport = self._transport_factory()
        client = ResilientHttpClient(
            FetchPolicy(
                allowed_hosts=(authorization_boundary,),
                timeout_seconds=self._settings.external_io_timeout_seconds,
                max_attempts=1,
                base_backoff_seconds=0.0,
                rate_limit_per_minute=6,
                minimum_interval_seconds=1,
                circuit_failure_threshold=1,
                circuit_reset_seconds=60.0,
                max_redirects=1,
                user_agent="SRBGQualificationProbe/1.0",
                max_response_bytes=512 * 1024,
            ),
            resolver=self._resolver,
            transport=transport,
            clock=self._clock,
        )
        try:
            result = await client.get(
                robots_url,
                checkpoint=SourceCheckpoint(),
                accept="text/plain",
                allow_not_found=True,
            )
        except (OSError, SsrfRejected) as error:
            raise QualificationExecutionError("TARGET_ROBOTS_UNAVAILABLE") from error
        finally:
            await transport.close()
        if result.status_code in {404, 410}:
            return EvidenceReview.NOT_PRESENT
        content = result.content or b""
        response_hash = result.response_sha256 or sha256(content).hexdigest()
        lines = content.decode("utf-8", errors="ignore").splitlines()
        if not any(line.strip().casefold().startswith("user-agent:") for line in lines):
            return EvidenceReview.RESTRICTED
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(lines)
        if not parser.can_fetch("SRBGQualificationProbe/1.0", target_url):
            raise QualificationPolicyBlocked(
                "ROBOTS_BLOCKED",
                evidence_fingerprint=response_hash,
            )
        return EvidenceReview.ALLOWED


class QualificationExecutor:
    def __init__(
        self,
        *,
        gateway: QualificationGateway,
        provider: SearchProvider,
        target_probe: TargetProbe,
    ) -> None:
        self._gateway = gateway
        self._provider = provider
        self._target_probe = target_probe

    async def run(
        self,
        *,
        qualification_run_id: UUID,
    ) -> QualificationOutcome:
        binding: QualificationBinding | None = None
        try:
            binding = await self._gateway.acquire(qualification_run_id)
            if binding is None:
                return QualificationOutcome(
                    qualification_run_id,
                    acquired=False,
                    status="ALREADY_CLAIMED",
                    target_evidence_count=0,
                )
            try:
                hits = await self._provider.discover_targets(binding)
                evidences: list[SafeTargetEvidence] = []
                seen_targets: set[str] = set()
                for hit in hits:
                    target_key = _authorized_target_key(
                        hit.url,
                        authorization_boundary=binding.authorization_boundary,
                    )
                    if target_key is None or target_key in seen_targets:
                        continue
                    seen_targets.add(target_key)
                    evidence = await self._target_probe.probe(
                        hit.url,
                        authorization_boundary=binding.authorization_boundary,
                    )
                    _validate_probed_evidence(binding, hit.url, evidence)
                    if not evidence.raw_evidence_storage_prohibited:
                        await self._gateway.record_target_evidence(binding, evidence)
                    evidences.append(evidence)
                summary = _summarize_qualification(binding, evidences)
                terminal = await self._gateway.complete(binding, summary)
                return QualificationOutcome(
                    qualification_run_id,
                    acquired=True,
                    status=terminal,
                    target_evidence_count=len(evidences),
                )
            except QualificationPolicyBlocked as error:
                summary = _summarize_policy_block(binding, error)
                terminal = await self._gateway.complete(binding, summary)
                return QualificationOutcome(
                    qualification_run_id,
                    acquired=True,
                    status=terminal,
                    target_evidence_count=0,
                )
            except QualificationExecutionError as error:
                terminal = await self._gateway.fail(binding, reason_code=error.reason_code)
                return QualificationOutcome(
                    qualification_run_id,
                    acquired=True,
                    status=terminal,
                    target_evidence_count=0,
                )
        finally:
            await self._gateway.close()


class ActivationOutboxExecutor:
    def __init__(
        self,
        *,
        gateway: ActivationOutboxGateway,
        dispatch_source_fetch: Callable[[UUID, UUID], Awaitable[None]],
    ) -> None:
        self._gateway = gateway
        self._dispatch_source_fetch = dispatch_source_fetch

    async def run(self, outbox_id: UUID) -> ActivationOutcome:
        dispatch = await self._gateway.prepare(outbox_id)
        if dispatch is None:
            return ActivationOutcome(outbox_id, None, None, "ALREADY_CLAIMED", False)
        if not dispatch.needs_dispatch:
            return ActivationOutcome(
                dispatch.outbox_id,
                dispatch.source_id,
                dispatch.fetch_run_id,
                "SUCCEEDED",
                False,
            )
        await self._dispatch_source_fetch(dispatch.source_id, dispatch.fetch_run_id)
        if not await self._gateway.mark_succeeded(dispatch):
            raise RuntimeError("activation outbox completion lost its database lease")
        return ActivationOutcome(
            dispatch.outbox_id,
            dispatch.source_id,
            dispatch.fetch_run_id,
            "SUCCEEDED",
            True,
        )


class PostgresQualificationGateway:
    """Qualification-only lease and private target-evidence persistence."""

    def __init__(
        self,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
        object_store: S3ObjectStore | None = None,
        malware_scanner: ClamAVScanner | None = None,
    ) -> None:
        self._engine = engine or create_database_engine(settings)
        self._object_store = object_store or S3ObjectStore(settings)
        self._malware_scanner = malware_scanner or ClamAVScanner(
            settings.clamav_host,
            settings.clamav_port,
            settings.external_io_timeout_seconds,
        )

    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
        bounded_limit = max(1, min(limit, 100))
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(_PENDING_QUALIFICATION_IDS_SQL),
                        {"now": datetime.now(UTC), "limit": bounded_limit},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(row["id"] for row in rows if isinstance(row.get("id"), UUID))

    async def acquire(
        self,
        qualification_run_id: UUID,
    ) -> QualificationBinding | None:
        now = datetime.now(UTC)
        lease_token = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_ACQUIRE_QUALIFICATION_SQL),
                        {
                            "qualification_run_id": qualification_run_id,
                            "lease_token": lease_token,
                            "now": now,
                            "leased_until": now + timedelta(minutes=10),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _qualification_binding_from_row(
            row,
            qualification_run_id=qualification_run_id,
        )

    async def record_target_evidence(
        self,
        binding: QualificationBinding,
        evidence: SafeTargetEvidence,
    ) -> UUID:
        _validate_probed_evidence(binding, evidence.capture.requested_url, evidence)
        capture = evidence.capture
        try:
            await self._malware_scanner.scan(capture.content)
        except (MalwareDetected, MalwareScanInconclusive) as error:
            raise QualificationExecutionError("TARGET_SECURITY_REJECTED") from error
        content_hash = sha256(capture.content).hexdigest()
        object_key = f"qualification/sha256/{content_hash[:2]}/{content_hash}"
        await self._object_store.put_if_absent(
            object_key,
            capture.content,
            "application/octet-stream",
        )
        capture_id = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_RECORD_TARGET_EVIDENCE_SQL),
                        {
                            "capture_id": capture_id,
                            "qualification_run_id": binding.qualification_run_id,
                            "candidate_id": binding.candidate_id,
                            "lease_token": binding.lease_token,
                            "purpose": "TARGET_PAGE",
                            "requested_url": capture.requested_url,
                            "final_url": capture.final_url,
                            "object_key": object_key,
                            "content_sha256": content_hash,
                            "response_sha256": capture.response_sha256,
                            "byte_size": len(capture.content),
                            "http_status": capture.status_code,
                            "content_type": _bounded_content_type(capture.content_type),
                            "captured_at": capture.captured_at,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        identifier = None if row is None else row.get("id")
        if not isinstance(identifier, UUID):
            raise QualificationExecutionError("QUALIFICATION_CAPTURE_NOT_AUTHORIZED")
        return identifier

    async def complete(
        self,
        binding: QualificationBinding,
        summary: QualificationSummary,
    ) -> str:
        prepared = (
            binding.prepared_source_id,
            binding.prepared_policy_version_id,
            binding.prepared_connector_config_version_id,
            binding.prepared_trial_run_id,
        )
        if summary.verdict != "BLOCKED" and any(value is None for value in prepared):
            raise QualificationExecutionError("PRODUCTION_PREPARATION_MISSING")
        bundle_id = uuid7()
        checks = [
            {
                "code": check.code,
                "level": check.outcome,
                "message": "Shared source qualification policy evaluated direct target evidence.",
                "evidence_refs": [f"qualification-run:{binding.qualification_run_id}"],
                "observed_at": summary.created_at.isoformat(),
            }
            for check in summary.checks
        ]
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_COMPLETE_QUALIFICATION_SQL),
                        {
                            "bundle_id": bundle_id,
                            "qualification_run_id": binding.qualification_run_id,
                            "candidate_id": binding.candidate_id,
                            "lease_token": binding.lease_token,
                            "rule_version": binding.rule_version,
                            "expected_material_fingerprint": binding.material_fingerprint,
                            "material_fingerprint": summary.evidence_fingerprint,
                            "verdict": summary.verdict,
                            "storage_policy": summary.storage_policy,
                            "evidence_capture_policy": summary.evidence_capture_policy,
                            "checks": json.dumps(
                                checks,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            "reason_codes": list(summary.reason_codes),
                            "sampled_item_count": summary.sampled_item_count,
                            "relevant_item_count": summary.relevant_item_count,
                            "now": summary.created_at,
                            "valid_until": summary.valid_until,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise QualificationExecutionError("QUALIFICATION_COMPLETION_NOT_AUTHORIZED")
        return "SUCCEEDED"

    async def fail(self, binding: QualificationBinding, *, reason_code: str) -> str:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_FAIL_QUALIFICATION_SQL),
                        {
                            "qualification_run_id": binding.qualification_run_id,
                            "candidate_id": binding.candidate_id,
                            "lease_token": binding.lease_token,
                            "reason_code": _reason_code(reason_code),
                            "now": datetime.now(UTC),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        return "FAILED" if row is not None else "LEASE_LOST"

    async def close(self) -> None:
        await self._engine.dispose()


class PostgresActivationOutboxGateway:
    """Create a fresh production run from an activation outbox fact."""

    def __init__(
        self,
        settings: Settings,
        *,
        engine: AsyncEngine | None = None,
    ) -> None:
        self._engine = engine or create_database_engine(settings)

    async def pending_ids(self, *, limit: int) -> tuple[UUID, ...]:
        bounded_limit = max(1, min(limit, 100))
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(_PENDING_ACTIVATION_IDS_SQL),
                        {"now": datetime.now(UTC), "limit": bounded_limit},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(row["id"] for row in rows if isinstance(row.get("id"), UUID))

    async def prepare(self, outbox_id: UUID) -> ActivationDispatch | None:
        now = datetime.now(UTC)
        fetch_run_id = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_PREPARE_ACTIVATION_SQL),
                        {
                            "outbox_id": outbox_id,
                            "fetch_run_id": fetch_run_id,
                            "now": now,
                            "leased_until": now + timedelta(minutes=10),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return _activation_dispatch_from_row(row)

    async def mark_succeeded(self, dispatch: ActivationDispatch) -> bool:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(_MARK_ACTIVATION_SUCCEEDED_SQL),
                        {
                            "outbox_id": dispatch.outbox_id,
                            "source_id": dispatch.source_id,
                            "fetch_run_id": dispatch.fetch_run_id,
                            "now": datetime.now(UTC),
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        return row is not None

    async def close(self) -> None:
        await self._engine.dispose()


def _qualification_binding_from_row(
    row: RowMapping | dict[str, object],
    *,
    qualification_run_id: UUID,
) -> QualificationBinding:
    return QualificationBinding(
        qualification_run_id=qualification_run_id,
        candidate_id=_required_uuid(row.get("candidate_id")),
        campaign_id=_optional_uuid(row.get("campaign_id")),
        canonical_url=str(row["canonical_url"]),
        authorization_boundary=str(row["authorization_boundary"]),
        rule_version=str(row["rule_version"]),
        material_fingerprint=str(row["material_fingerprint"]),
        lease_token=_required_uuid(row.get("lease_token")),
        prepared_source_id=_optional_uuid(row.get("prepared_source_id")),
        prepared_policy_version_id=_optional_uuid(row.get("prepared_policy_version_id")),
        prepared_connector_config_version_id=_optional_uuid(
            row.get("prepared_connector_config_version_id")
        ),
        prepared_trial_run_id=_optional_uuid(row.get("prepared_trial_run_id")),
    )


def _activation_dispatch_from_row(
    row: RowMapping | dict[str, object],
) -> ActivationDispatch:
    needs_dispatch = row.get("needs_dispatch")
    if not isinstance(needs_dispatch, bool):
        raise RuntimeError("activation dispatch state is invalid")
    return ActivationDispatch(
        outbox_id=_required_uuid(row.get("outbox_id")),
        source_id=_required_uuid(row.get("source_id")),
        fetch_run_id=_required_uuid(row.get("fetch_run_id")),
        needs_dispatch=needs_dispatch,
    )


def _summarize_qualification(
    binding: QualificationBinding,
    evidences: list[SafeTargetEvidence],
) -> QualificationSummary:
    material_fingerprint = binding.material_fingerprint
    evidence_fingerprint = _qualification_evidence_fingerprint(binding, evidences)
    prepared = (
        binding.prepared_source_id,
        binding.prepared_policy_version_id,
        binding.prepared_connector_config_version_id,
        binding.prepared_trial_run_id,
    )
    facts = QualificationFacts(
        canonical_url=binding.canonical_url,
        authorization_boundary=binding.authorization_boundary,
        robots=_strictest_review(evidence.robots for evidence in evidences),
        terms=_strictest_review(evidence.terms for evidence in evidences),
        copyright=_strictest_review(evidence.copyright for evidence in evidences),
        requires_login=any(evidence.requires_login for evidence in evidences),
        captcha_detected=any(evidence.captcha_detected for evidence in evidences),
        paywall_detected=any(evidence.paywall_detected for evidence in evidences),
        redirect_boundary_valid=bool(evidences)
        and all(evidence.redirect_boundary_valid for evidence in evidences),
        resolved_addresses_public=bool(evidences)
        and all(evidence.resolved_addresses_public for evidence in evidences),
        connector_valid=bool(evidences)
        and all(evidence.connector_valid for evidence in evidences)
        and all(value is not None for value in prepared),
        relevant_item_count=sum(1 for evidence in evidences if evidence.relevant),
        sampled_item_count=len(evidences),
        material_fingerprint=material_fingerprint,
        raw_evidence_storage_prohibited=any(
            evidence.raw_evidence_storage_prohibited for evidence in evidences
        ),
        qualification_evidence_fingerprint=evidence_fingerprint,
    )
    assessment = evaluate_qualification(
        facts,
        rule_version=binding.rule_version,
    )
    check_outcome = {
        "QUALIFIED": "PASS",
        "WARN_WAIVABLE": "WARN",
        "BLOCKED": "BLOCK",
    }[assessment.verdict.value]
    return QualificationSummary(
        material_fingerprint=material_fingerprint,
        evidence_fingerprint=evidence_fingerprint,
        verdict=assessment.verdict.value,
        storage_policy=assessment.storage_policy.value,
        evidence_capture_policy=assessment.evidence_capture_policy.value,
        checks=(QualificationCheck("SHARED_POLICY_EVALUATION", check_outcome),),
        reason_codes=assessment.reason_codes,
        sampled_item_count=assessment.sampled_item_count,
        relevant_item_count=assessment.relevant_item_count,
        bundle_sha256=assessment.bundle_sha256,
        created_at=assessment.created_at,
        valid_until=assessment.expires_at,
    )


def _summarize_policy_block(
    binding: QualificationBinding,
    error: QualificationPolicyBlocked,
) -> QualificationSummary:
    facts = QualificationFacts(
        canonical_url=binding.canonical_url,
        authorization_boundary=binding.authorization_boundary,
        robots=EvidenceReview.BLOCKED,
        terms=EvidenceReview.NOT_PRESENT,
        copyright=EvidenceReview.NOT_PRESENT,
        requires_login=False,
        captcha_detected=False,
        paywall_detected=False,
        redirect_boundary_valid=True,
        resolved_addresses_public=True,
        connector_valid=True,
        relevant_item_count=0,
        sampled_item_count=0,
        material_fingerprint=binding.material_fingerprint,
        raw_evidence_storage_prohibited=True,
        qualification_evidence_fingerprint=error.evidence_fingerprint,
    )
    assessment = evaluate_qualification(facts, rule_version=binding.rule_version)
    return QualificationSummary(
        material_fingerprint=binding.material_fingerprint,
        evidence_fingerprint=error.evidence_fingerprint,
        verdict=assessment.verdict.value,
        storage_policy=assessment.storage_policy.value,
        evidence_capture_policy=assessment.evidence_capture_policy.value,
        checks=(QualificationCheck(error.reason_code, "BLOCK"),),
        reason_codes=assessment.reason_codes,
        sampled_item_count=assessment.sampled_item_count,
        relevant_item_count=assessment.relevant_item_count,
        bundle_sha256=assessment.bundle_sha256,
        created_at=assessment.created_at,
        valid_until=assessment.expires_at,
    )


def _qualification_evidence_fingerprint(
    binding: QualificationBinding,
    evidences: Iterable[SafeTargetEvidence],
) -> str:
    """Bind the decision bundle to the direct target bytes reviewed in isolation."""

    response_hashes = sorted(evidence.capture.response_sha256 for evidence in evidences)
    material = "\n".join(
        (
            binding.canonical_url,
            binding.authorization_boundary,
            *(response_hashes or ["NO_TARGET_EVIDENCE"]),
        )
    )
    return sha256(material.encode("utf-8")).hexdigest()


_ENGINEERING_RELEVANCE_TERMS = (
    "公路",
    "路桥",
    "桥梁",
    "隧道",
    "铁路",
    "轨道交通",
    "水利",
    "市政工程",
    "建筑工程",
    "能源工程",
    "港口",
    "航道",
    "机场工程",
    "交通运输",
    "交通工程",
    "工程建设",
    "工程施工",
    "数字化转型",
    "数智化",
    "物联网",
    "低空设备",
    "无人机",
    "人工智能",
    "安全生产",
    "安全管理",
    "安全规定",
    "事故调查",
    "事故通报",
    "处罚决定",
    "整改案例",
    "engineering",
    "infrastructure",
    "highway",
    "bridge",
    "tunnel",
    "railway",
    "rail transit",
    "water conservancy",
    "municipal construction",
    "construction safety",
    "accident investigation",
    "digital transformation",
    "internet of things",
    "artificial intelligence",
)


def _target_is_engineering_relevant(url: str, content: bytes) -> bool:
    """Use only direct target material, never paid-search snippets, for relevance."""

    sample = content[: 2 * 1024 * 1024]
    decoded_variants = (
        sample.decode("utf-8", errors="ignore"),
        sample.decode("gb18030", errors="ignore"),
    )
    searchable = f"{url}\n{' '.join(decoded_variants)}".casefold()
    return any(term.casefold() in searchable for term in _ENGINEERING_RELEVANCE_TERMS)


def _generic_connector_valid(result: FetchResult, authorization_boundary: str) -> bool:
    if result.content is None:
        return False
    try:
        records = ListDetailConnector().discover(
            result,
            {
                "list_url": result.url,
                "allowed_hosts": [authorization_boundary],
                "item_selector": "a",
                "link_selector": "a",
                "title_selector": "a",
            },
        )
    except DeclarativeParseError:
        return False
    return bool(records)


def _strictest_review(values: Iterable[EvidenceReview]) -> EvidenceReview:
    reviews = tuple(values)
    for review in (
        EvidenceReview.BLOCKED,
        EvidenceReview.RESTRICTED,
        EvidenceReview.NOT_PRESENT,
        EvidenceReview.ALLOWED,
    ):
        if review in reviews:
            return review
    return EvidenceReview.NOT_PRESENT


def _validate_probed_evidence(
    binding: QualificationBinding,
    requested_url: str,
    evidence: SafeTargetEvidence,
) -> None:
    capture = evidence.capture
    if capture.requested_url != requested_url:
        raise QualificationExecutionError("TARGET_REQUEST_URL_MISMATCH")
    if not evidence.resolved_addresses_public:
        raise QualificationExecutionError("TARGET_ADDRESS_NOT_PUBLIC")
    if not evidence.redirect_boundary_valid:
        raise QualificationExecutionError("TARGET_REDIRECT_BOUNDARY_INVALID")
    if (
        _authorized_target_key(
            capture.requested_url,
            authorization_boundary=binding.authorization_boundary,
        )
        is None
        or _authorized_target_key(
            capture.final_url,
            authorization_boundary=binding.authorization_boundary,
        )
        is None
    ):
        raise QualificationExecutionError("TARGET_OUTSIDE_AUTHORIZATION_BOUNDARY")
    if not 200 <= capture.status_code < 300:
        raise QualificationExecutionError("TARGET_HTTP_STATUS_REJECTED")


def _authorized_target_key(url: str, *, authorization_boundary: str) -> str | None:
    if not _valid_boundary(authorization_boundary):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    hostname = None if parts.hostname is None else parts.hostname.rstrip(".").casefold()
    if (
        parts.scheme.casefold() != "https"
        or hostname != authorization_boundary.casefold()
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        return None
    return parts.geturl()


def _is_https_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parts.scheme.casefold() == "https"
        and parts.hostname
        and parts.username is None
        and parts.password is None
    )


def _valid_boundary(value: str) -> bool:
    return bool(
        1 <= len(value) <= 253
        and value == value.rstrip(".").casefold()
        and re.fullmatch(r"[a-z0-9.-]+", value)
        and ".." not in value
        and not value.startswith((".", "-"))
        and not value.endswith((".", "-"))
    )


def _bounded_content_type(value: str) -> str:
    candidate = value.split(";", 1)[0].strip().casefold()
    return candidate if 1 <= len(candidate) <= 100 else "application/octet-stream"


def _target_access_signals(content: bytes) -> tuple[bool, bool, bool]:
    sample = content[:1_000_000].decode("utf-8", errors="ignore").casefold()
    requires_login = any(
        marker in sample
        for marker in (
            "登录后查看",
            "登录后继续",
            "sign in to continue",
            "login required",
        )
    )
    captcha_detected = any(
        marker in sample
        for marker in (
            "请输入验证码",
            "完成验证码",
            "captcha challenge",
            "verify you are human",
        )
    )
    paywall_detected = any(
        marker in sample
        for marker in (
            "订阅后阅读全文",
            "付费后阅读",
            "subscribe to continue reading",
            "subscriber-only content",
        )
    )
    return requires_login, captcha_detected, paywall_detected


def _reason_code(value: str) -> str:
    candidate = value.upper().replace("-", "_").replace(" ", "_")
    return candidate if re.fullmatch(r"[A-Z0-9_]{1,100}", candidate) else "UNKNOWN"


def _required_uuid(value: object) -> UUID:
    if not isinstance(value, UUID):
        raise RuntimeError("authoritative identifier is missing")
    return value


def _optional_uuid(value: object) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    raise RuntimeError("authoritative identifier is invalid")


_PENDING_QUALIFICATION_IDS_SQL = """
SELECT qualification_run_id AS id
  FROM list_pending_source_qualification_ids(:now,:limit)
"""

_ACQUIRE_QUALIFICATION_SQL = """
SELECT * FROM acquire_source_qualification(
  :qualification_run_id,:lease_token,:now,:leased_until
)
"""

_RECORD_TARGET_EVIDENCE_SQL = """
SELECT record_source_qualification_capture(
  :capture_id,:qualification_run_id,:candidate_id,:lease_token,:purpose,
  :requested_url,:final_url,:object_key,:content_sha256,:response_sha256,
  :byte_size,:http_status,:content_type,:captured_at
) AS id
"""

_COMPLETE_QUALIFICATION_SQL = """
SELECT complete_source_qualification(
  :bundle_id,:qualification_run_id,:candidate_id,:lease_token,:rule_version,
  :expected_material_fingerprint,:material_fingerprint,:verdict,:storage_policy,
  :evidence_capture_policy,CAST(:checks AS jsonb),:reason_codes,
  :sampled_item_count,:relevant_item_count,:now,:valid_until
) AS id
"""

_FAIL_QUALIFICATION_SQL = """
SELECT fail_source_qualification(
  :qualification_run_id,:candidate_id,:lease_token,:reason_code,:now
) AS id
"""

_PENDING_ACTIVATION_IDS_SQL = """
SELECT outbox_id AS id FROM list_pending_source_activation_ids(:now,:limit)
"""

_PREPARE_ACTIVATION_SQL = """
SELECT * FROM prepare_source_activation(
  :outbox_id,:fetch_run_id,:now,:leased_until
)
"""

_MARK_ACTIVATION_SUCCEEDED_SQL = """
SELECT complete_source_activation(
  :outbox_id,:fetch_run_id,:source_id,:now
) AS id
"""
