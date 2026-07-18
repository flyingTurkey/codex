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


class PostgresAiAdminService:
    def __init__(self, engine: AsyncEngine, *, secret_root: Path, environment: str) -> None:
        self._engine = engine
        self._environment = environment.casefold()
        self._secrets = LocalAiSecretStore(root=secret_root, environment=environment)

    async def providers(self) -> list[dict[str, object]]:
        async with self._engine.connect() as connection:
            active_rows = await connection.execute(
                text(
                    "SELECT DISTINCT ON (provider) provider,active FROM ai_provider_activation "
                    "WHERE environment=:environment ORDER BY provider,created_at DESC,id DESC"
                ),
                {"environment": self._environment},
            )
            activations = {str(row.provider): bool(row.active) for row in active_rows}
        views: list[dict[str, object]] = []
        for capability in provider_catalog():
            key_configured = self._secrets.is_configured(capability.code)
            reasons: list[str] = []
            if capability.code is ProviderCode.DEEPSEEK and not key_configured:
                reasons.append("SECRET_NOT_CONFIGURED")
            if not activations.get(capability.code.value, False):
                reasons.append("CONFIGURATION_NOT_ACTIVE")
            if not capability.real_call_enabled:
                reasons.append("MOCK_ONLY")
            views.append(
                {
                    "code": capability.code.value,
                    "base_url": capability.base_url,
                    "request_path": capability.request_path,
                    "models": list(capability.models),
                    "real_call_enabled": capability.real_call_enabled,
                    "key_configured": key_configured,
                    "runtime_status": "READY" if not reasons else "MODEL_DISABLED",
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
