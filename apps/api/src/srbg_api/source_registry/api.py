"""Administrative source registry and raw-document HTTP API."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from srbg_contracts import (
    ConnectorConfigPreview,
    ConnectorConfigPreviewRequest,
    ConnectorConfigRequest,
    ConnectorConfigVersionView,
    ConnectorDefinitionView,
    CreateSourceRequest,
    DocumentDetail,
    FixtureUploadResponse,
    MeResponse,
    SourceActionRequest,
    SourceAssessmentSubmission,
    SourceAuditEventView,
    SourceCoverageMatrix,
    SourceDetail,
    SourceEligibility,
    SourceGovernanceMetadataUpdate,
    SourceLifecycleAction,
    SourceLifecycleActionRequest,
    SourceLifecycleEventView,
    SourceOnboardingSubmission,
    SourcePolicyDecisionRequest,
    SourcePolicySubmission,
    SourcePolicyV2Submission,
    SourcePolicyVersionView,
    SourceProductionApprovalRequest,
    SourceSummary,
    SourceTransitionRequest,
    SourceTrialRunRequest,
    SourceTrialRunView,
    UserRole,
)

from srbg_api.auth import (
    Principal,
    get_current_principal,
    require_roles,
    require_roles_with_step_up,
)
from srbg_api.config import Settings, get_settings
from srbg_api.source_registry.service import ROUND17_ROSTER_COHORT

READ_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN, UserRole.AUDITOR)
WRITE_ROLES = (UserRole.SOURCE_ADMIN, UserRole.PLATFORM_ADMIN)
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
ReadPrincipal = Annotated[Principal, Depends(require_roles(*READ_ROLES))]
WritePrincipal = Annotated[Principal, Depends(require_roles_with_step_up(*WRITE_ROLES))]
CurrentSettings = Annotated[Settings, Depends(get_settings)]
FixtureFilename = Annotated[
    str,
    Header(alias="X-Filename", min_length=1, max_length=255),
]
FixtureCanonicalUrl = Annotated[
    str,
    Header(alias="X-Document-URL", min_length=1, max_length=2048),
]


async def _read_fixture_body(request: Request, max_bytes: int) -> bytes:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Fixture is too large",
            )
        content.extend(chunk)
    return bytes(content)


def _fixture_content_length(request: Request, max_bytes: int) -> int | None:
    values = request.headers.getlist("content-length")
    if not values:
        return None
    value = values[0]
    if (
        len(values) != 1
        or not value.isascii()
        or not value.isdigit()
        or (len(value) > 1 and value.startswith("0"))
    ):
        raise HTTPException(status_code=400, detail="Invalid Content-Length")
    declared_length = int(value)
    if declared_length > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Fixture is too large",
        )
    return declared_length


class AdminSourceService(Protocol):
    async def list_sources(self) -> list[SourceSummary]: ...

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def get_source(self, source_id: UUID) -> SourceDetail: ...

    async def get_eligibility(self, source_id: UUID) -> SourceEligibility: ...

    async def assign_round17_governance_scheme(
        self,
        source_id: UUID,
        *,
        cohort_key: str,
        reason: str,
        actor_id: UUID,
        actor_display_name: str,
        oidc_issuer: str,
        oidc_subject: str,
        request_id: str,
    ) -> None: ...

    async def save_policy(
        self,
        source_id: UUID,
        payload: SourcePolicySubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def save_onboarding(
        self,
        source_id: UUID,
        payload: SourceOnboardingSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def transition(
        self,
        source_id: UUID,
        payload: SourceTransitionRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def set_enabled(
        self,
        source_id: UUID,
        enabled: bool,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def submit_policy_version(
        self,
        source_id: UUID,
        payload: SourcePolicyV2Submission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourcePolicyVersionView: ...

    async def list_policy_versions(
        self, source_id: UUID
    ) -> list[SourcePolicyVersionView]: ...

    async def decide_policy_version(
        self,
        source_id: UUID,
        policy_id: UUID,
        payload: SourcePolicyDecisionRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourcePolicyVersionView: ...

    async def start_trial_run(
        self,
        source_id: UUID,
        payload: SourceTrialRunRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceTrialRunView: ...

    async def list_trial_runs(self, source_id: UUID) -> list[SourceTrialRunView]: ...

    async def complete_fixture_trial(
        self,
        source_id: UUID,
        trial_id: UUID,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceTrialRunView: ...

    async def approve_production(
        self,
        source_id: UUID,
        payload: SourceProductionApprovalRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def list_lifecycle_events(
        self, source_id: UUID
    ) -> list[SourceLifecycleEventView]: ...

    async def list_audit_events(self, source_id: UUID) -> list[SourceAuditEventView]: ...

    async def source_coverage(self) -> SourceCoverageMatrix: ...

    async def list_connector_definitions(self) -> list[ConnectorDefinitionView]: ...

    async def preview_connector_config(
        self, source_id: UUID, payload: ConnectorConfigPreviewRequest
    ) -> ConnectorConfigPreview: ...

    async def save_connector_config(
        self,
        source_id: UUID,
        payload: ConnectorConfigRequest,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> ConnectorConfigVersionView: ...

    async def list_connector_configs(
        self, source_id: UUID
    ) -> list[ConnectorConfigVersionView]: ...

    async def update_governance_metadata(
        self,
        source_id: UUID,
        payload: SourceGovernanceMetadataUpdate,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def append_assessments(
        self,
        source_id: UUID,
        payload: SourceAssessmentSubmission,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

    async def lifecycle_action(
        self,
        source_id: UUID,
        action: str,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
    ) -> SourceDetail: ...

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
    ) -> FixtureUploadResponse: ...

    async def get_document(self, document_id: UUID) -> DocumentDetail: ...


router = APIRouter(prefix="/api/v1", tags=["source-vault"])


def _service(request: Request) -> AdminSourceService:
    service = getattr(request.app.state, "source_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Source vault service is unavailable",
        )
    return cast(AdminSourceService, service)


@router.get("/me", response_model=MeResponse)
async def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        display_name=principal.display_name,
        roles=sorted(principal.roles, key=lambda role: role.value),
        local_identity=principal.local_identity,
    )


@router.get("/admin/sources", response_model=list[SourceSummary])
async def list_sources(
    request: Request,
    _: ReadPrincipal,
) -> list[SourceSummary]:
    return await _service(request).list_sources()


@router.get("/admin/source-coverage", response_model=SourceCoverageMatrix)
async def source_coverage(
    request: Request,
    _: ReadPrincipal,
) -> SourceCoverageMatrix:
    return await _service(request).source_coverage()


@router.get(
    "/admin/connector-definitions", response_model=list[ConnectorDefinitionView]
)
async def list_connector_definitions(
    request: Request,
    _: ReadPrincipal,
) -> list[ConnectorDefinitionView]:
    return await _service(request).list_connector_definitions()


@router.post("/admin/sources", response_model=SourceDetail, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: CreateSourceRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).create_source(
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/sources/{source_id}", response_model=SourceDetail)
async def get_source(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> SourceDetail:
    return await _service(request).get_source(source_id)


@router.post(
    "/admin/sources/{source_id}/round17-governance-assignment",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def assign_round17_governance_scheme(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
    settings: CurrentSettings,
) -> None:
    trusted_actor_id = settings.round17_leo_approver_actor_id
    if (
        principal.local_identity
        or trusted_actor_id is None
        or principal.user_id != trusted_actor_id
        or principal.display_name != "LEO"
        or principal.oidc_issuer is None
        or principal.oidc_subject is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Round 17 governance requires the attested LEO source approver",
        )
    await _service(request).assign_round17_governance_scheme(
        source_id,
        cohort_key=ROUND17_ROSTER_COHORT,
        reason=payload.reason,
        actor_id=principal.user_id,
        actor_display_name=principal.display_name,
        oidc_issuer=principal.oidc_issuer,
        oidc_subject=principal.oidc_subject,
        request_id=request.state.request_id,
    )


@router.put(
    "/admin/sources/{source_id}/governance-metadata", response_model=SourceDetail
)
async def update_governance_metadata(
    source_id: UUID,
    payload: SourceGovernanceMetadataUpdate,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).update_governance_metadata(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/assessments", response_model=SourceDetail)
async def append_source_assessments(
    source_id: UUID,
    payload: SourceAssessmentSubmission,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).append_assessments(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get(
    "/admin/sources/{source_id}/connector-config-versions",
    response_model=list[ConnectorConfigVersionView],
)
async def list_connector_configs(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> list[ConnectorConfigVersionView]:
    return await _service(request).list_connector_configs(source_id)


@router.post(
    "/admin/sources/{source_id}/connector-config-versions/preview",
    response_model=ConnectorConfigPreview,
)
async def preview_connector_config(
    source_id: UUID,
    payload: ConnectorConfigPreviewRequest,
    request: Request,
    _: WritePrincipal,
) -> ConnectorConfigPreview:
    return await _service(request).preview_connector_config(source_id, payload)


@router.post(
    "/admin/sources/{source_id}/connector-config-versions",
    response_model=ConnectorConfigVersionView,
    status_code=status.HTTP_201_CREATED,
)
async def save_connector_config(
    source_id: UUID,
    payload: ConnectorConfigRequest,
    request: Request,
    principal: WritePrincipal,
) -> ConnectorConfigVersionView:
    return await _service(request).save_connector_config(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/sources/{source_id}/eligibility", response_model=SourceEligibility)
async def get_eligibility(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> SourceEligibility:
    return await _service(request).get_eligibility(source_id)


@router.put("/admin/sources/{source_id}/policy", response_model=SourceDetail)
async def save_policy(
    source_id: UUID,
    payload: SourcePolicySubmission,
    request: Request,
    _: WritePrincipal,
) -> SourceDetail:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy source policy writes are retired",
        headers={
            "Link": (
                f"</api/v1/admin/sources/{source_id}/policy-versions>; "
                'rel="successor-version"'
            )
        },
    )


@router.post("/admin/sources/{source_id}/onboarding-records", response_model=SourceDetail)
async def save_onboarding(
    source_id: UUID,
    payload: SourceOnboardingSubmission,
    request: Request,
    _: WritePrincipal,
) -> SourceDetail:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy onboarding writes are retired",
        headers={
            "Link": f"</api/v1/admin/sources/{source_id}/trial-runs>; rel=\"successor-version\""
        },
    )


@router.post("/admin/sources/{source_id}/transitions", response_model=SourceDetail)
async def transition(
    source_id: UUID,
    payload: SourceTransitionRequest,
    request: Request,
    _: WritePrincipal,
) -> SourceDetail:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy state writes are retired",
        headers={
            "Link": f"</api/v1/admin/sources/{source_id}/approve>; rel=\"successor-version\""
        },
    )


@router.post("/admin/sources/{source_id}/enable", response_model=SourceDetail)
async def enable_source(
    source_id: UUID,
    payload: SourceActionRequest,
    request: Request,
    _: WritePrincipal,
) -> SourceDetail:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy enable is retired",
        headers={
            "Link": f"</api/v1/admin/sources/{source_id}/approve>; rel=\"successor-version\""
        },
    )


@router.post("/admin/sources/{source_id}/disable", response_model=SourceDetail)
async def disable_source(
    source_id: UUID,
    payload: SourceActionRequest,
    request: Request,
    _: WritePrincipal,
) -> SourceDetail:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy disable is retired",
        headers={
            "Link": f"</api/v1/admin/sources/{source_id}/pause>; rel=\"successor-version\""
        },
    )


async def _run_lifecycle_action(
    source_id: UUID,
    action: SourceLifecycleAction,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: Principal,
) -> SourceDetail:
    return await _service(request).lifecycle_action(
        source_id,
        action.value,
        payload.reason,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/submit-compliance", response_model=SourceDetail)
async def submit_compliance(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _run_lifecycle_action(
        source_id, SourceLifecycleAction.SUBMIT_COMPLIANCE, payload, request, principal
    )


@router.get(
    "/admin/sources/{source_id}/policy-versions",
    response_model=list[SourcePolicyVersionView],
)
async def list_policy_versions(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> list[SourcePolicyVersionView]:
    return await _service(request).list_policy_versions(source_id)


@router.post(
    "/admin/sources/{source_id}/policy-versions",
    response_model=SourcePolicyVersionView,
    status_code=status.HTTP_201_CREATED,
)
async def submit_policy_version(
    source_id: UUID,
    payload: SourcePolicyV2Submission,
    request: Request,
    principal: WritePrincipal,
) -> SourcePolicyVersionView:
    return await _service(request).submit_policy_version(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post(
    "/admin/sources/{source_id}/policy-versions/{policy_id}/decisions",
    response_model=SourcePolicyVersionView,
)
async def decide_policy_version(
    source_id: UUID,
    policy_id: UUID,
    payload: SourcePolicyDecisionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourcePolicyVersionView:
    return await _service(request).decide_policy_version(
        source_id,
        policy_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get(
    "/admin/sources/{source_id}/trial-runs",
    response_model=list[SourceTrialRunView],
)
async def list_trial_runs(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> list[SourceTrialRunView]:
    return await _service(request).list_trial_runs(source_id)


@router.post(
    "/admin/sources/{source_id}/trial-runs",
    response_model=SourceTrialRunView,
    status_code=status.HTTP_201_CREATED,
)
async def start_trial_run(
    source_id: UUID,
    payload: SourceTrialRunRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceTrialRunView:
    return await _service(request).start_trial_run(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post(
    "/admin/sources/{source_id}/trial-runs/{trial_id}/complete-fixture",
    response_model=SourceTrialRunView,
)
async def complete_fixture_trial(
    source_id: UUID,
    trial_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceTrialRunView:
    return await _service(request).complete_fixture_trial(
        source_id,
        trial_id,
        payload.reason,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.post("/admin/sources/{source_id}/approve", response_model=SourceDetail)
async def approve_source(
    source_id: UUID,
    payload: SourceProductionApprovalRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _service(request).approve_production(
        source_id,
        payload,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get(
    "/admin/sources/{source_id}/lifecycle-events",
    response_model=list[SourceLifecycleEventView],
)
async def list_lifecycle_events(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> list[SourceLifecycleEventView]:
    return await _service(request).list_lifecycle_events(source_id)


@router.get(
    "/admin/sources/{source_id}/audit-events",
    response_model=list[SourceAuditEventView],
)
async def list_source_audit_events(
    source_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> list[SourceAuditEventView]:
    return await _service(request).list_audit_events(source_id)


@router.post("/admin/sources/{source_id}/pause", response_model=SourceDetail)
async def pause_source(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _run_lifecycle_action(
        source_id, SourceLifecycleAction.PAUSE, payload, request, principal
    )


@router.post("/admin/sources/{source_id}/resume", response_model=SourceDetail)
async def resume_source(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _run_lifecycle_action(
        source_id, SourceLifecycleAction.RESUME, payload, request, principal
    )


@router.post("/admin/sources/{source_id}/retire", response_model=SourceDetail)
async def retire_source(
    source_id: UUID,
    payload: SourceLifecycleActionRequest,
    request: Request,
    principal: WritePrincipal,
) -> SourceDetail:
    return await _run_lifecycle_action(
        source_id, SourceLifecycleAction.RETIRE, payload, request, principal
    )


@router.post(
    "/admin/sources/{source_id}/fixture",
    response_model=FixtureUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_fixture(
    source_id: UUID,
    request: Request,
    principal: WritePrincipal,
    filename: FixtureFilename,
    canonical_url: FixtureCanonicalUrl,
) -> FixtureUploadResponse:
    max_fixture_bytes = get_settings().fixture_max_bytes
    declared_length = _fixture_content_length(request, max_fixture_bytes)
    content = await _read_fixture_body(request, max_fixture_bytes)
    if declared_length is not None and declared_length != len(content):
        raise HTTPException(
            status_code=400,
            detail="Content-Length does not match the fixture body",
        )
    return await _service(request).upload_fixture(
        source_id,
        content=content,
        filename=filename,
        declared_mime=request.headers.get("content-type", ""),
        canonical_url=canonical_url,
        actor_id=principal.user_id,
        request_id=request.state.request_id,
    )


@router.get("/admin/documents/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: UUID,
    request: Request,
    _: ReadPrincipal,
) -> DocumentDetail:
    return await _service(request).get_document(document_id)
