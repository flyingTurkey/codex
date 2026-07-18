"""Fail-closed administrative API for pinned AI capabilities and write-only Secrets."""

from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from srbg_api.ai_pipeline.catalog import ProviderCode, provider_capability
from srbg_api.ai_pipeline.secrets import SecretStorageDisabled
from srbg_api.auth import Principal, require_local_owner


class AiAdminService(Protocol):
    async def providers(self) -> list[dict[str, object]]: ...

    async def activate(self, *, provider: ProviderCode, model: str, actor_id: UUID) -> UUID: ...

    async def put_secret(self, *, provider: ProviderCode, secret: str, actor_id: UUID) -> None: ...


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiConfigurationRequest(_StrictModel):
    provider: ProviderCode
    model: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def approved_model(self) -> "AiConfigurationRequest":
        if self.model not in provider_capability(self.provider).models:
            raise ValueError("model is not in the pinned provider catalog")
        return self


class AiConfigurationResponse(_StrictModel):
    id: UUID
    status: str = "ACTIVE"


class AiSecretRequest(_StrictModel):
    api_key: SecretStr = Field(min_length=1, max_length=4096)


ReadPrincipal = Annotated[
    Principal,
    Depends(require_local_owner),
]
WritePrincipal = Annotated[
    Principal,
    Depends(require_local_owner),
]

router = APIRouter(prefix="/api/v1/settings/ai", tags=["personal-settings"])


def _service(request: Request) -> AiAdminService:
    service = request.app.state.ai_admin_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MODEL_DISABLED: AI administration is unavailable",
        )
    return cast(AiAdminService, service)


@router.get("/providers")
async def list_providers(request: Request, _: ReadPrincipal) -> list[dict[str, object]]:
    return await _service(request).providers()


@router.post(
    "/configurations",
    response_model=AiConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_configuration(
    payload: AiConfigurationRequest,
    request: Request,
    principal: WritePrincipal,
) -> AiConfigurationResponse:
    configuration_id = await _service(request).activate(
        provider=payload.provider,
        model=payload.model,
        actor_id=principal.user_id,
    )
    return AiConfigurationResponse(id=configuration_id)


@router.put("/providers/{provider}/secret", status_code=status.HTTP_204_NO_CONTENT)
async def put_secret(
    payload: AiSecretRequest,
    request: Request,
    principal: WritePrincipal,
    provider: Annotated[ProviderCode, Path()],
) -> Response:
    try:
        await _service(request).put_secret(
            provider=provider,
            secret=payload.api_key.get_secret_value(),
            actor_id=principal.user_id,
        )
    except SecretStorageDisabled as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MODEL_DISABLED: local Secret writes are disabled",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
