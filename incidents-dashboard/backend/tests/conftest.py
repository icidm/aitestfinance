import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# Set test env before importing app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["DATABASE_URL_SYNC"] = "sqlite:///./test.db"
os.environ["SECRET_KEY"] = "test-secret-key-32-chars-minimum-123456"
os.environ["CORS_ORIGINS"] = "http://localhost:8000"

from app.main import app
from app.db import get_session
from app.models import Base, User
from app.auth import get_password_hash

TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="session")
async def engine():
    # Remove existing test db
    if os.path.exists("./test.db"):
        os.remove("./test.db")
    eng = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    # Enable WAL for better concurrency
    from sqlalchemy import event
    @event.listens_for(eng.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Also set pragma via connection
        await conn.execute(text("PRAGMA journal_mode=WAL;"))
    yield eng
    await eng.dispose()
    if os.path.exists("./test.db"):
        os.remove("./test.db")

@pytest_asyncio.fixture
async def session(engine):
    async_session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as sess:
        # Create users if not exist
        from sqlalchemy import select
        res = await sess.execute(select(User).where(User.username=="admin"))
        if not res.scalar_one_or_none():
            for uname, pwd, role in [("viewer","Viewer123!","viewer"),("operator","Operator123!","operator"),("admin","Admin123!","admin")]:
                u = User(username=uname, hashed_password=get_password_hash(pwd), role=role)
                sess.add(u)
            await sess.commit()
        # Seed incidents if empty
        from app.models import Incident
        res2 = await sess.execute(select(Incident))
        if not res2.scalars().first():
            from app.crud import seed_database
            await seed_database(sess)
            await sess.commit()
        yield sess
        await sess.rollback()

@pytest_asyncio.fixture
async def client(engine, session):
    # Override to create fresh session per request to avoid sqlite locking on concurrent requests
    async def override_get_session():
        async_session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        async with async_session() as sess:
            yield sess
    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

async def login(client, username, password):
    res = await client.post("/api/auth/login", data={"username": username, "password": password}, headers={"Content-Type":"application/x-www-form-urlencoded"})
    return res

@pytest_asyncio.fixture
async def viewer_token(client):
    r = await login(client, "viewer", "Viewer123!")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

@pytest_asyncio.fixture
async def operator_token(client):
    r = await login(client, "operator", "Operator123!")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

@pytest_asyncio.fixture
async def admin_token(client):
    r = await login(client, "admin", "Admin123!")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

@pytest_asyncio.fixture
async def admin_refresh(client):
    r = await login(client, "admin", "Admin123!")
    return r.json()["refresh_token"]
