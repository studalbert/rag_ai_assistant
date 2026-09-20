import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.api.chat as chat_router_module
import app.services.chat_service as chat_service_module
from app.models.chat import Chat, Message
from app.models.chunk import EMBEDDING_DIM, Chunk
from app.models.enums import MessageRole
from app.schemas.chat import SourceChunk
from app.services.chat_service import ChatService
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


class FakeLLMProvider:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens

    async def stream_completion(self, messages: list[dict[str, str]]):
        for token in self.tokens:
            yield token


class FailingLLMProvider:
    async def stream_completion(self, messages: list[dict[str, str]]):
        raise RuntimeError("LLM unavailable")
        yield  # noqa: unreachable — нужен, чтобы функция осталась async-генератором


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
    return events


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


# --- build_prompt: чистая функция, без БД и HTTP ---


def test_build_prompt_includes_system_and_numbered_sources() -> None:
    service = ChatService.__new__(ChatService)  # build_prompt не трогает self, конструктор не нужен
    sources = [
        SourceChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            filename="doc1.txt",
            content="First chunk content",
            similarity=0.9,
        ),
        SourceChunk(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            filename="doc2.txt",
            content="Second chunk content",
            similarity=0.7,
        ),
    ]

    messages = service.build_prompt("What is this about?", sources)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "[1]" in messages[1]["content"]
    assert "[2]" in messages[1]["content"]
    assert "doc1.txt" in messages[1]["content"]
    assert "First chunk content" in messages[1]["content"]
    assert "What is this about?" in messages[1]["content"]


def test_build_prompt_handles_no_sources() -> None:
    service = ChatService.__new__(ChatService)

    messages = service.build_prompt("Question with no matches", [])

    assert "не нашлось релевантных фрагментов" in messages[1]["content"]


# --- /ask/stream: стриминг + сохранение истории, с моком LLM ---


@pytest.mark.asyncio
async def test_ask_stream_saves_question_and_answer_to_history(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    vector = _unit_vector(seed=1.0)
    await _insert_document_with_chunk(workspace_id, "doc.txt", "Relevant content", vector)

    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(
        chat_router_module, "get_llm_provider", lambda: FakeLLMProvider(["Hello", ", ", "world!"])
    )

    response = await client.post(
        f"/workspaces/{workspace_id}/ask/stream",
        json={"question": "What is in the document?"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)

    event_types = [event["type"] for event in events]
    assert event_types == ["chat_id", "sources", "token", "token", "token", "done"]

    tokens = [event["content"] for event in events if event["type"] == "token"]
    assert "".join(tokens) == "Hello, world!"

    chat_id = uuid.UUID(events[0]["chat_id"])

    async with TestSessionLocal() as session:
        chat = await session.get(Chat, chat_id)
        assert chat is not None
        assert chat.workspace_id == uuid.UUID(workspace_id)

        result = await session.execute(
            select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
        )
        messages = result.scalars().all()

    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "What is in the document?"
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[1].content == "Hello, world!"
    assert messages[1].source_chunk_ids is not None
    assert len(messages[1].source_chunk_ids) == 1


@pytest.mark.asyncio
async def test_ask_stream_continues_existing_chat(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    vector = _unit_vector(seed=1.0)
    await _insert_document_with_chunk(workspace_id, "doc.txt", "Content", vector)

    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(chat_router_module, "get_llm_provider", lambda: FakeLLMProvider(["Answer"]))

    first_response = await client.post(
        f"/workspaces/{workspace_id}/ask/stream",
        json={"question": "First question"},
        headers=_auth_headers(token),
    )
    chat_id = _parse_sse(first_response.text)[0]["chat_id"]

    second_response = await client.post(
        f"/workspaces/{workspace_id}/ask/stream",
        json={"question": "Second question", "chat_id": chat_id},
        headers=_auth_headers(token),
    )
    second_chat_id = _parse_sse(second_response.text)[0]["chat_id"]

    assert second_chat_id == chat_id  # тот же чат, не создался новый

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(Message).where(Message.chat_id == uuid.UUID(chat_id))
        )
        messages = result.scalars().all()

    assert len(messages) == 4  # 2 вопроса + 2 ответа


@pytest.mark.asyncio
async def test_ask_stream_with_foreign_chat_id_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")

    alice_workspace_id = await _create_workspace(client, alice_token, "Alice's workspace")
    bob_workspace_id = await _create_workspace(client, bob_token, "Bob's workspace")

    vector = _unit_vector(seed=1.0)
    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(chat_router_module, "get_llm_provider", lambda: FakeLLMProvider(["x"]))

    # Алиса получает chat_id в своём workspace...
    alice_response = await client.post(
        f"/workspaces/{alice_workspace_id}/ask/stream",
        json={"question": "test"},
        headers=_auth_headers(alice_token),
    )
    alice_chat_id = _parse_sse(alice_response.text)[0]["chat_id"]

    # ...Боб пытается продолжить этот чат в СВОЁМ workspace — должен получить 404
    bob_response = await client.post(
        f"/workspaces/{bob_workspace_id}/ask/stream",
        json={"question": "test", "chat_id": alice_chat_id},
        headers=_auth_headers(bob_token),
    )

    assert bob_response.status_code == 404


@pytest.mark.asyncio
async def test_ask_stream_llm_failure_does_not_save_incomplete_answer(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    vector = _unit_vector(seed=1.0)
    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(chat_router_module, "get_llm_provider", lambda: FailingLLMProvider())

    response = await client.post(
        f"/workspaces/{workspace_id}/ask/stream",
        json={"question": "test"},
        headers=_auth_headers(token),
    )

    assert response.status_code == 200  # заголовки уже ушли до сбоя LLM
    events = _parse_sse(response.text)
    assert events[-1]["type"] == "error"
    assert "LLM unavailable" in events[-1]["message"]

    chat_id = uuid.UUID(events[0]["chat_id"])

    async with TestSessionLocal() as session:
        result = await session.execute(select(Message).where(Message.chat_id == chat_id))
        messages = result.scalars().all()

    assert messages == []  # ничего не сохранилось — ответ был неполным
