import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    """Хелпер: регистрирует пользователя и возвращает его access_token."""
    payload = {"email": email, "password": "secret123"}
    await client.post("/auth/register", json=payload)
    response = await client.post("/auth/login", json=payload)
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")

    response = await client.post(
        "/workspaces", json={"name": "My first workspace"}, headers=_auth_headers(token)
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My first workspace"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_workspace_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/workspaces", json={"name": "No auth"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_workspaces_returns_only_own(client: AsyncClient) -> None:
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")

    await client.post(
        "/workspaces", json={"name": "Alice's workspace"}, headers=_auth_headers(alice_token)
    )
    await client.post(
        "/workspaces", json={"name": "Bob's workspace"}, headers=_auth_headers(bob_token)
    )

    alice_response = await client.get("/workspaces", headers=_auth_headers(alice_token))
    alice_workspaces = alice_response.json()

    assert alice_response.status_code == 200
    assert len(alice_workspaces) == 1
    assert alice_workspaces[0]["name"] == "Alice's workspace"


@pytest.mark.asyncio
async def test_cannot_delete_another_users_workspace(client: AsyncClient) -> None:
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")

    create_response = await client.post(
        "/workspaces", json={"name": "Alice's workspace"}, headers=_auth_headers(alice_token)
    )
    workspace_id = create_response.json()["id"]

    # Боб пытается удалить workspace Алисы — должен получить 404, а не 403
    # (мы намеренно скрываем сам факт существования чужого workspace)
    delete_response = await client.delete(
        f"/workspaces/{workspace_id}", headers=_auth_headers(bob_token)
    )
    assert delete_response.status_code == 404

    # workspace Алисы должен остаться на месте
    alice_list = await client.get("/workspaces", headers=_auth_headers(alice_token))
    assert len(alice_list.json()) == 1


@pytest.mark.asyncio
async def test_owner_can_delete_own_workspace(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")

    create_response = await client.post(
        "/workspaces", json={"name": "To be deleted"}, headers=_auth_headers(token)
    )
    workspace_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/workspaces/{workspace_id}", headers=_auth_headers(token)
    )
    assert delete_response.status_code == 204

    list_response = await client.get("/workspaces", headers=_auth_headers(token))
    assert list_response.json() == []