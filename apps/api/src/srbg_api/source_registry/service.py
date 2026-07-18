"""Owner-only personal source application service."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from srbg_contracts import (
    DiscoveryDailyUsageView,
    DiscoverySettingPatchRequest,
    DiscoverySettingView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    PersonalSourceActivityItemView,
    PersonalSourceActivityPage,
    PersonalSourceCreateRequest,
    PersonalSourcePatchRequest,
    PersonalSourceReprobeRequest,
    PersonalSourceRunSummaryView,
    PersonalSourceStreamView,
    PersonalSourceView,
    SourceAutoScoreDetailView,
    SourceProfileOverrideRequest,
    SourceProfileView,
    StreamProbeRunView,
)

from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.document_vault.scanner import ClamAVScanner
from srbg_api.document_vault.service import (
    DocumentVaultService,
    SourceVaultMetrics,
    VaultRepository,
)
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.observability import (
    PERSONAL_SOURCE_UPDATES,
)
from srbg_api.pdf_processing.security import FileSecurityPolicy
from srbg_api.source_registry.repository import (
    PersonalSourceRow,
    SourceVaultRepository,
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
        repository: Any,
        document_vault: DocumentVaultService,
        *,
        baidu_search_enabled: bool = False,
        baidu_search_key_configured: bool = False,
    ) -> None:
        self._repository = repository
        self._document_vault = document_vault
        self._baidu_search_enabled = baidu_search_enabled
        self._baidu_search_key_configured = baidu_search_key_configured
        self.metrics = document_vault.metrics

    @property
    def document_vault(self) -> DocumentVaultService:
        return self._document_vault

    async def close(self) -> None:
        await self._repository.close()

    async def list_personal_sources(self) -> list[PersonalSourceView]:
        return [
            _personal_source_view(row) for row in await self._repository.list_personal_sources()
        ]

    async def get_personal_source(self, source_id: UUID) -> PersonalSourceView:
        return _personal_source_view(await self._repository.get_personal_source(source_id))

    async def get_personal_source_activity(
        self, source_id: UUID, *, cursor: str | None, limit: int
    ) -> PersonalSourceActivityPage:
        page = await self._repository.get_personal_source_activity(
            source_id, cursor=cursor, limit=limit
        )
        return PersonalSourceActivityPage(
            items=[
                PersonalSourceActivityItemView(
                    id=item.id,
                    kind=item.kind,
                    occurred_at=item.occurred_at,
                    stream_id=item.stream_id,
                    status=item.status,
                    reason_code=item.reason_code,
                    discovered_count=item.discovered_count,
                    fetched_count=item.fetched_count,
                    failed_count=item.failed_count,
                )
                for item in page.items
            ],
            next_cursor=page.next_cursor,
            run_summary=PersonalSourceRunSummaryView(
                last_run_at=page.run_summary.last_run_at,
                last_run_status=page.run_summary.last_run_status,
                discovered_count=page.run_summary.discovered_count,
                fetched_count=page.run_summary.fetched_count,
                failed_count=page.run_summary.failed_count,
                next_run_at=page.run_summary.next_run_at,
            ),
        )

    async def get_discovery_setting(self) -> DiscoverySettingView:
        row = await self._repository.get_discovery_setting()
        return DiscoverySettingView(
            automation_enabled=row.automation_enabled,
            discovery_interval_seconds=21600,
            next_run_at=row.updated_at + timedelta(seconds=21600)
            if row.automation_enabled
            else None,
            baidu_status="DISABLED"
            if not self._baidu_search_enabled
            else "AVAILABLE"
            if self._baidu_search_key_configured
            else "KEY_MISSING",
            updated_at=row.updated_at,
        )

    async def patch_discovery_setting(
        self, payload: DiscoverySettingPatchRequest, *, actor_id: UUID, request_id: str
    ) -> DiscoverySettingView:
        enabled = payload.automation_enabled
        if enabled is None:
            raise SourceServiceRejected("automation_enabled must not be null", 422)
        await self._repository.patch_discovery_setting(
            enabled, actor_id=actor_id, request_id=request_id, now=_now()
        )
        return await self.get_discovery_setting()

    async def list_discovery_topics(self) -> list[DiscoveryTopicView]:
        return cast(list[DiscoveryTopicView], await self._repository.list_discovery_topics())

    async def patch_discovery_topic(
        self,
        topic_id: UUID,
        payload: DiscoveryTopicPatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> DiscoveryTopicView:
        return cast(
            DiscoveryTopicView,
            await self._repository.patch_discovery_topic(
                topic_id, payload, actor_id=actor_id, request_id=request_id, now=_now()
            ),
        )

    async def get_discovery_usage(self) -> DiscoveryDailyUsageView:
        return cast(DiscoveryDailyUsageView, await self._repository.get_discovery_usage(now=_now()))

    async def get_auto_score(self, source_id: UUID) -> SourceAutoScoreDetailView:
        return cast(SourceAutoScoreDetailView, await self._repository.get_auto_score(source_id))

    async def get_source_profile(self, source_id: UUID) -> SourceProfileView:
        return cast(SourceProfileView, await self._repository.get_source_profile(source_id))

    async def patch_source_profile_override(
        self,
        source_id: UUID,
        payload: SourceProfileOverrideRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceProfileView:
        profile = await self._repository.patch_source_profile_override(
            source_id, payload, actor_id=actor_id, request_id=request_id, now=_now()
        )
        _log_governance_action(
            event_name="source_profile_override_updated",
            action="PROFILE_OVERRIDE",
            outcome="SUCCEEDED",
            reason_code="OWNER_PROFILE_OVERRIDE",
            request_id=request_id,
            source_id=source_id,
        )
        return cast(SourceProfileView, profile)

    async def revoke_source_profile_override(
        self, source_id: UUID, *, actor_id: UUID, request_id: str
    ) -> SourceProfileView:
        profile = await self._repository.revoke_source_profile_override(
            source_id, actor_id=actor_id, request_id=request_id, now=_now()
        )
        _log_governance_action(
            event_name="source_profile_override_revoked",
            action="PROFILE_OVERRIDE_REVOKE",
            outcome="SUCCEEDED",
            reason_code="OWNER_PROFILE_OVERRIDE_REVOKED",
            request_id=request_id,
            source_id=source_id,
        )
        return cast(SourceProfileView, profile)

    async def patch_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourcePatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView:
        action = (
            "intent_and_name"
            if payload.model_fields_set == {"desired_enabled", "display_name"}
            else "intent"
            if "desired_enabled" in payload.model_fields_set
            else "display_name"
        )
        row = await self._repository.patch_personal_source(
            source_id, payload, actor_id=actor_id, request_id=request_id, now=_now()
        )
        PERSONAL_SOURCE_UPDATES.labels(action, "succeeded").inc()
        _log_governance_action(
            event_name="personal_source_updated",
            action=action.upper(),
            outcome="SUCCEEDED",
            reason_code="OWNER_INTENT_RECORDED",
            request_id=request_id,
            source_id=source_id,
        )
        return _personal_source_view(row)

    async def create_personal_source(
        self, payload: PersonalSourceCreateRequest, *, actor_id: UUID, request_id: str
    ) -> PersonalSourceView:
        try:
            row = await self._repository.create_personal_source(
                payload, actor_id=actor_id, request_id=request_id, now=_now()
            )
        except ValueError as error:
            raise SourceServiceRejected(str(error), 422) from error
        return _personal_source_view(row)

    async def reprobe_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourceReprobeRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> PersonalSourceView:
        row = await self._repository.reprobe_personal_source(
            source_id, payload, actor_id=actor_id, request_id=request_id, now=_now()
        )
        return _personal_source_view(row)


def build_default_source_service(settings: Settings) -> SourceRegistryService:
    engine = create_database_engine(settings)
    repository = SourceVaultRepository(engine)
    metrics = SourceVaultMetrics()
    vault = DocumentVaultService(
        repository=cast(VaultRepository, repository),
        object_store=S3ObjectStore(settings),
        malware_scanner=ClamAVScanner(
            settings.clamav_host, settings.clamav_port, settings.external_io_timeout_seconds
        ),
        metrics=metrics,
        max_fixture_bytes=settings.fixture_max_bytes,
        max_pdf_pages=settings.fixture_max_pdf_pages,
        file_security_policy=_file_security_policy(settings),
    )
    return SourceRegistryService(
        repository,
        vault,
        baidu_search_enabled=settings.baidu_search_enabled,
        baidu_search_key_configured=bool(
            settings.baidu_search_api_key and settings.baidu_search_api_key.get_secret_value()
        ),
    )


def _personal_source_view(row: PersonalSourceRow) -> PersonalSourceView:
    return PersonalSourceView(
        id=row.id,
        display_name=row.display_name,
        url=row.url,
        desired_enabled=row.desired_enabled,
        runtime_state=row.runtime_state,
        manual_disabled_at=row.manual_disabled_at,
        normalized_origin=row.normalized_origin,
        streams=[
            PersonalSourceStreamView(
                id=stream.id,
                stream_type=stream.stream_type,
                normalized_url=stream.normalized_url,
                allowed_hosts=list(stream.allowed_hosts),
                config_sha256=stream.config_sha256,
                discovery_method=stream.discovery_method,
                status=stream.status,
                failure_reason=stream.failure_reason,
                actual_running=stream.actual_running,
                runtime_state=stream.runtime_state,
                health_status=stream.health_status,
                health_reason=stream.health_reason,
                consecutive_failures=stream.consecutive_failures,
                next_self_heal_at=stream.next_self_heal_at,
                last_successful_fetch_at=stream.last_successful_fetch_at,
                last_content_discovered_at=stream.last_content_discovered_at,
                health_observation_id=stream.health_observation_id,
                health_observed_at=stream.health_observed_at,
            )
            for stream in row.streams
        ],
        latest_probe_run=None
        if row.latest_probe_run is None
        else StreamProbeRunView(
            id=row.latest_probe_run.id,
            requested_url=row.latest_probe_run.requested_url,
            input_kind=row.latest_probe_run.input_kind,
            status=row.latest_probe_run.status,
            duration_ms=row.latest_probe_run.duration_ms,
            failure_code=row.latest_probe_run.failure_code,
            failure_reason=row.latest_probe_run.failure_reason,
        ),
        auto_score_summary=row.auto_score_summary,
        profile_summary=row.profile_summary,
    )


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


def _now() -> datetime:
    return datetime.now(UTC)
