"""PostgreSQL engine construction for explicit application services."""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from srbg_api.config import Settings


def create_database_engine(settings: Settings, *, database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        database_url or settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def create_publication_engine(settings: Settings) -> AsyncEngine:
    return create_database_engine(settings, database_url=settings.publication_database_url)
