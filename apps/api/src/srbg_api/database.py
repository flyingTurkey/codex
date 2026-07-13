"""PostgreSQL engine construction for explicit application services."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from srbg_api.config import Settings


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )
