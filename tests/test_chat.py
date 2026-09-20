import uuid

import pytest
from httpx import AsyncClient

import app.services.chat_service as chat_service_module
from app.models.chunk import EMBEDDING_DIM, Chunk
from tests.conftest import TestSessionLocal


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


def _unit_vector(seed: float) -> list[float]:
    """Простой детерминированный вектор для тестов — направление важнее конкретных чисел."""
    vector = [0.0] * EMBEDDING_DIM
    vector[0] = seed
    vector[1] = 1.0
    return vector


async def _insert_document_with_chunk(
    workspace_id: str, filename: str, content: str, embedding: list[float]
) -> None:
    async with TestSessionLocal() as session:
        from app.models.document import Document
        from app.models.enums import DocumentStatus

        document = Document(
            workspace_id=uuid.UUID(workspace_id),
            filename=filename,
            file_path="/dev/null",
            content_type="text/plain",
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(document_id=document.id, content=content, order_index=0, embedding=embedding)
        session.add(chunk)
        await session.commit()


class FakeQueryEmbeddingProvider:
    """Возвращает вектор, максимально близкий (по направлению) к 'релевантному' чанку."""

    def __init__(self, query_vector: list[float]):
        self.query_vector = query_vector

    async def embed_query(self, text: str) -> list[float]:
        return self.query_vector


@pytest.mark.asyncio
async def test_ask_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/workspaces/00000000-0000-0000-0000-000000000000/ask", json={"question": "test"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ask_on_nonexistent_workspace_returns_404(client: AsyncClient) -> None:
    token = await _register_and_login(client, "alice@example.com")
    fake_workspace_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"/workspaces/{fake_workspace_id}/ask",
        json={"question": "test"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_ask_returns_most_similar_chunk_first(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    # relevant: вектор совпадает по направлению с запросом; irrelevant: почти противоположный
    relevant_vector = _unit_vector(seed=1.0)
    irrelevant_vector = _unit_vector(seed=-1.0)

    await _insert_document_with_chunk(
        workspace_id, "relevant.txt", "This chunk should match", relevant_vector
    )
    await _insert_document_with_chunk(
        workspace_id, "irrelevant.txt", "This chunk should not match", irrelevant_vector
    )

    monkeypatch.setattr(
        chat_service_module,
        "get_embedding_provider",
        lambda: FakeQueryEmbeddingProvider(relevant_vector),
    )

    response = await client.post(
        f"/workspaces/{workspace_id}/ask",
        json={"question": "irrelevant text, provider is mocked anyway", "top_k": 2},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    sources = response.json()["sources"]
    assert len(sources) == 2
    assert sources[0]["filename"] == "relevant.txt"
    assert sources[0]["similarity"] > sources[1]["similarity"]


@pytest.mark.asyncio
async def test_ask_only_searches_within_own_workspace(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")

    alice_workspace_id = await _create_workspace(client, alice_token, "Alice's workspace")
    bob_workspace_id = await _create_workspace(client, bob_token, "Bob's workspace")

    vector = _unit_vector(seed=1.0)
    await _insert_document_with_chunk(bob_workspace_id, "bob_doc.txt", "Bob's content", vector)

    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )

    # Алиса спрашивает свой (пустой) workspace — не должна увидеть чанк Боба
    response = await client.post(
        f"/workspaces/{alice_workspace_id}/ask",
        json={"question": "test"},
        headers=_auth_headers(alice_token),
    )

    assert response.status_code == 200
    assert response.json()["sources"] == []
