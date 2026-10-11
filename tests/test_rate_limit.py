import pytest
from httpx import AsyncClient


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
