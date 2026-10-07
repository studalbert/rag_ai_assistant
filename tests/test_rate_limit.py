import pytest
from httpx import AsyncClient

from app.core.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """slowapi хранит счётчики в памяти процесса — общие для всех тестов,
    если не сбрасывать явно между ними. Без этого один тест мог бы "съесть"
    лимит, из-за которого упал бы совершенно другой, не связанный тест."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.mark.asyncio
async def test_register_rate_limited_after_five_requests(client: AsyncClient) -> None:
    for i in range(5):
        response = await client.post(
            "/auth/register",
            json={"email": f"user{i}@example.com", "password": "secret123"},
        )
        assert response.status_code == 201

    response = await client.post(
        "/auth/register",
        json={"email": "user6@example.com", "password": "secret123"},
    )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_login_rate_limited_after_ten_requests(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "secret123"}
    )

    for _ in range(10):
        response = await client.post(
            "/auth/login",
            json={"email": "alice@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 401

    response = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 429
