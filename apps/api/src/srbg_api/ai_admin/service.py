"""PostgreSQL-backed append-only AI configuration service."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.ai_pipeline.budget import BudgetPolicy
from srbg_api.ai_pipeline.catalog import ProviderCode, provider_capability, provider_catalog
from srbg_api.ai_pipeline.secrets import LocalAiSecretStore
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.ai_runtime import (
    AiAvailabilityFacts,
    project_ai_availability,
)
from srbg_api.observability import T06_AI_RUNTIME_STATE


class PostgresAiAdminService:
    def __init__(self, engine: AsyncEngine, *, secret_root: Path, environment: str) -> None:
        self._engine = engine
        self._environment = environment.casefold()
        self._secrets = LocalAiSecretStore(root=secret_root, environment=environment)

    async def providers(self) -> list[dict[str, object]]:
        async with self._engine.connect() as connection:
            active_rows = await connection.execute(
                text(
                    "SELECT DISTINCT ON (activation.provider) activation.provider,"
                    "activation.active,profile.model FROM ai_provider_activation activation "
                    "JOIN ai_model_profile profile ON profile.id=activation.model_profile_id "
                    "WHERE activation.environment=:environment ORDER BY activation.provider,"
                    "activation.created_at DESC,activation.id DESC"
                ),
                {"environment": self._environment},
            )
            activations = {
                str(row.provider): (bool(row.active), str(row.model)) for row in active_rows
            }
            runtime_rows = await connection.execute(
                text(
                    "SELECT DISTINCT ON (provider) provider,model,worker_heartbeat_at,"
                    "queue_healthy,budget_healthy,last_real_schema_success_at "
                    "FROM ai_runtime_observation_v2 WHERE environment=:environment "
                    "ORDER BY provider,observed_at DESC,id DESC"
                ),
                {"environment": self._environment},
            )
            runtime = {str(row.provider): row for row in runtime_rows}
            success_rows = await connection.execute(
                text(
                    "SELECT provider,model,max(succeeded_at) AS succeeded_at "
                    "FROM ai_approved_content_success_v2 WHERE environment=:environment "
                    "AND success_kind='APPROVED_CONTENT' GROUP BY provider,model"
                ),
                {"environment": self._environment},
            )
            successes = {
                (str(row.provider), str(row.model)): row.succeeded_at for row in success_rows
            }
        views: list[dict[str, object]] = []
        for capability in provider_catalog():
            key_configured = self._secrets.is_configured(capability.code)
            activation = activations.get(capability.code.value)
            configuration_active = bool(activation and activation[0])
            configured_model = activation[1] if activation else capability.models[0]
            health = runtime.get(capability.code.value)
            now = datetime.now(UTC)
            availability = project_ai_availability(
                AiAvailabilityFacts(
                    configuration_active=configuration_active,
                    secret_configured=key_configured,
                    provider=capability.code.value,
                    configured_model=configured_model,
                    worker_provider=(capability.code.value if health is not None else None),
                    worker_model=(str(health.model) if health is not None else None),
                    worker_heartbeat_at=(
                        health.worker_heartbeat_at if health is not None else None
                    ),
                    queue_healthy=bool(health and health.queue_healthy),
                    budget_healthy=bool(health and health.budget_healthy),
                    last_approved_content_schema_success_at=successes.get(
                        (capability.code.value, configured_model)
                    ),
                ),
                now=now,
            )
            T06_AI_RUNTIME_STATE.labels(
                provider=capability.code.value, state="configured"
            ).set(int(availability.configured))
            T06_AI_RUNTIME_STATE.labels(
                provider=capability.code.value, state="available"
            ).set(int(availability.available))
            reasons = list(availability.blocking_reasons)
            if not capability.real_call_enabled:
                reasons.append("MOCK_ONLY")
            configured = availability.configured
            available = availability.available and capability.real_call_enabled
            views.append(
                {
                    "code": capability.code.value,
                    "base_url": capability.base_url,
                    "request_path": capability.request_path,
                    "models": list(capability.models),
                    "real_call_enabled": capability.real_call_enabled,
                    "key_configured": key_configured,
                    "configured": configured,
                    "available": available,
                    "runtime_status": "AVAILABLE"
                    if available
                    else ("CONFIGURED_UNAVAILABLE" if configured else "NOT_CONFIGURED"),
                    "blocking_reasons": reasons,
                    "token_limits": {
                        "CLASSIFY": 1200,
                        "EXTRACT": 4000,
                        "SUMMARIZE": 1500,
                        "VERIFY": 1500,
                    },
                    "budget": (
                        {
                            "monthly_points": 20_000,
                            "document_points": 100,
                            "alert_points": 16_000,
                            "points_per_usd": 800,
                            "pricing_version": BudgetPolicy.deepseek_v4_flash().version,
                        }
                        if capability.code is ProviderCode.DEEPSEEK
                        else None
                    ),
                }
            )
        return views

    async def activate(self, *, provider: ProviderCode, model: str, actor_id: UUID) -> UUID:
        capability = provider_capability(provider)
        if model not in capability.models:
            raise ValueError("model is not approved")
        configuration_id = uuid7()
        profile_id = uuid7()
        now = datetime.now(UTC)
        policy = BudgetPolicy.deepseek_v4_flash()
        profile_version = f"ai01-{provider.value}-{model}-v1"
        if provider is ProviderCode.DEEPSEEK:
            input_price = policy.cache_miss_microusd_per_million
            output_price = policy.output_microusd_per_million
            pricing = policy.version
            parameters = (
                '{"thinking":{"type":"disabled"},'
                '"response_format":{"type":"json_object"},"temperature":0,'
                '"classify_max_tokens":1200,"extract_max_tokens":4000,'
                '"summarize_max_tokens":1500,"verify_max_tokens":1500}'
            )
        else:
            input_price, output_price, pricing = 0, 0, "mock-only-v1"
            parameters = '{"network_enabled":false}'
        async with self._engine.begin() as connection:
            existing = await connection.execute(
                text("SELECT id FROM ai_model_profile WHERE version=:version"),
                {"version": profile_version},
            )
            existing_id = existing.scalar_one_or_none()
            if existing_id is None:
                await connection.execute(
                    text(
                        "INSERT INTO ai_model_profile(id,version,provider,model,parameters,"
                        "pricing_version,input_price_microusd_per_million,"
                        "output_price_microusd_per_million,data_classifications,enabled,"
                        "created_at) "
                        "VALUES(:id,:version,:provider,:model,CAST(:parameters AS jsonb),:pricing,"
                        ":input_price,:output_price,ARRAY['PUBLIC_SOURCE'],true,:created_at)"
                    ),
                    {
                        "id": profile_id,
                        "version": profile_version,
                        "provider": provider.value,
                        "model": model,
                        "parameters": parameters,
                        "pricing": pricing,
                        "input_price": input_price,
                        "output_price": output_price,
                        "created_at": now,
                    },
                )
            else:
                profile_id = existing_id
            await connection.execute(
                text(
                    "INSERT INTO ai_provider_activation(id,provider,model_profile_id,environment,"
                    "active,created_by,created_at) VALUES(:id,:provider,:profile,:environment,"
                    "true,:actor,:created_at)"
                ),
                {
                    "id": configuration_id,
                    "provider": provider.value,
                    "profile": profile_id,
                    "environment": self._environment,
                    "actor": actor_id,
                    "created_at": now,
                },
            )
        return configuration_id

    async def put_secret(self, *, provider: ProviderCode, secret: str, actor_id: UUID) -> None:
        self._secrets.put(provider, secret)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ai_secret_change_audit(id,provider,action,environment,"
                    "actor_id,created_at) VALUES(:id,:provider,'PUT',:environment,:actor,:now)"
                ),
                {
                    "id": uuid7(),
                    "provider": provider.value,
                    "environment": self._environment,
                    "actor": actor_id,
                    "now": datetime.now(UTC),
                },
            )

    async def close(self) -> None:
        await self._engine.dispose()
