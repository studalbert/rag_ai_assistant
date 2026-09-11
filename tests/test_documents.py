import pytest
from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> str:
    payload = {"email": email, "password": "secret123"}
    await client.post("/auth/register", json=payload)
    response = await client.post("/auth/login", json=payload)
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_workspace(client: AsyncClient, token: str, name: str = "Test workspace") -> str:
    response = await client.post(
        "/workspaces", json={"name": name}, headers=_auth_headers(token)
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_upload_document_creates_pending_document(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    response = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "notes.txt"
    assert data["status"] == "pending"
    assert data["error_message"] is None


@pytest.mark.asyncio
async def test_upload_unsupported_content_type_returns_415(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    response = await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("data.json", b'{"a": 1}', "application/json")},
    )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_to_nonexistent_workspace_returns_404(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    fake_workspace_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"/workspaces/{fake_workspace_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_to_another_users_workspace_returns_404(client: AsyncClient) -> None:
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")
    alice_workspace_id = await _create_workspace(client, alice_token)

    response = await client.post(
        f"/workspaces/{alice_workspace_id}/documents",
        headers=_auth_headers(bob_token),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_without_token_returns_401(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    response = await client.post(
        f"/workspaces/{workspace_id}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_returns_uploaded_files(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    response = await client.get(
        f"/workspaces/{workspace_id}/documents", headers=_auth_headers(token)
    )

    assert response.status_code == 200
    documents = response.json()
    assert len(documents) == 1
    assert documents[0]["filename"] == "notes.txt"
