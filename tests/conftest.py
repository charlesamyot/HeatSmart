"""Shared test fixtures."""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_PATH", ":memory:")
os.environ.setdefault("ECONET_EMAIL", "test@example.com")
os.environ.setdefault("ECONET_PASSWORD", "testpassword")


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def app():
    """Create a test FastAPI app with in-memory DB."""
    from src.backend.database import init_db, close_db
    from src.backend.main import app as fastapi_app

    await init_db()
    yield fastapi_app
    await close_db()


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
