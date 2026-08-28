from typing import AsyncGenerator
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from .config import settings

# Determine async URL: env override else default sqlite
DATABASE_URL = settings.DATABASE_URL
DATABASE_URL_SYNC = settings.DATABASE_URL_SYNC


# Adjust engine kwargs depending on dialect
def _engine_kwargs(url: str):
    if url.startswith("sqlite"):
        return {"pool_pre_ping": True, "connect_args": {"check_same_thread": False}}
    # Postgres
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_async_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

# Enable WAL for SQLite to avoid fresh-session per-request DB locking and allow concurrent reads
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
        finally:
            cursor.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    # Import models to ensure metadata is loaded, then create tables if no alembic
    from .models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def health_check(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
