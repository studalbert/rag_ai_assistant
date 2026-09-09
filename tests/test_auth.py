import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_user(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "secret123"}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert "hashed_password" not in data  # пароль/хэш не должны утекать в ответ API


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "bob@example.com", "password": "secret123"}

    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_login_with_correct_password_returns_tokens(client: AsyncClient) -> None:
    payload = {"email": "carol@example.com", "password": "secret123"}
    await client.post("/auth/register", json=payload)

    response = await client.post("/auth/login", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "dave@example.com", "password": "secret123"}
    )

    response = await client.post(
        "/auth/login", json={"email": "dave@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_nonexistent_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer this-is-not-a-real-token"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token_returns_user(client: AsyncClient) -> None:
    payload = {"email": "erin@example.com", "password": "secret123"}
    await client.post("/auth/register", json=payload)
    login_response = await client.post("/auth/login", json=payload)
    access_token = login_response.json()["access_token"]

    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "erin@example.com"
