import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
from app.core.config import settings

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


_is_supabase = "supabase.co" in settings.database_url


def _parse_url(url: str) -> dict:
    url = url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
    url = url.split("?")[0]
    creds, rest = url.split("@", 1)
    user, password = creds.split(":", 1)
    if "/" in rest:
        host_part, db = rest.rsplit("/", 1)
    else:
        host_part, db = rest, "postgres"
    if ":" in host_part:
        host, port = host_part.rsplit(":", 1)
        port = int(port)
    else:
        host, port = host_part, 5432
    return {"user": user, "password": password, "host": host, "port": port, "database": db}


if _is_supabase:
    _params = _parse_url(settings.database_url)

    async def _async_creator():
        return await asyncpg.connect(
            **_params,
            ssl="require",
            statement_cache_size=0,
        )

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=_async_creator,
        poolclass=NullPool,
        echo=settings.debug,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    from app.models import user, inventory  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)