import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.api.chat as chat_router_module
import app.services.chat_service as chat_service_module
from app.core.config import settings
from app.models.chat import Chat, Message
from app.models.enums import MessageRole
from tests.conftest import TestSessionLocal
from tests.test_chat import (
    FakeLLMProvider,
    FakeQueryEmbeddingProvider,
    _auth_headers,
    _create_workspace,
    _register_and_login,
    _unit_vector,
)
from tests.test_web import _get_workspace_by_name, _register_web


async def _upload(client: AsyncClient, token: str, workspace_id: str, filename: str = "a.txt"):
    return await client.post(
        f"/workspaces/{workspace_id}/documents",
        headers=_auth_headers(token),
        files={"file": (filename, b"hello world", "text/plain")},
    )


async def _ask(client: AsyncClient, token: str, workspace_id: str):
    return await client.post(
        f"/workspaces/{workspace_id}/ask/stream",
        json={"question": "test question"},
        headers=_auth_headers(token),
    )


def _patch_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    vector = _unit_vector(seed=1.0)
    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(chat_router_module, "get_llm_provider", lambda: FakeLLMProvider(["ok"]))


# --- Лимит документов ---


@pytest.mark.asyncio
async def test_document_limit_blocks_extra_uploads(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_documents_per_user", 2)
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    assert (await _upload(client, token, workspace_id, "a.txt")).status_code == 201
    assert (await _upload(client, token, workspace_id, "b.txt")).status_code == 201

    response = await _upload(client, token, workspace_id, "c.txt")

    assert response.status_code == 402
    assert "лимит" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_document_limit_is_per_user_across_workspaces(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_documents_per_user", 2)
    token = await _register_and_login(client, "alice@example.com")
    first_workspace = await _create_workspace(client, token, "First")
    second_workspace = await _create_workspace(client, token, "Second")

    assert (await _upload(client, token, first_workspace)).status_code == 201
    assert (await _upload(client, token, second_workspace)).status_code == 201

    # Лимит общий на пользователя, а не на каждый workspace по отдельности
    assert (await _upload(client, token, first_workspace)).status_code == 402


@pytest.mark.asyncio
async def test_other_users_documents_do_not_count_toward_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_documents_per_user", 1)
    alice_token = await _register_and_login(client, "alice@example.com")
    bob_token = await _register_and_login(client, "bob@example.com")
    alice_workspace = await _create_workspace(client, alice_token, "Alice's")
    bob_workspace = await _create_workspace(client, bob_token, "Bob's")

    assert (await _upload(client, alice_token, alice_workspace)).status_code == 201
    assert (await _upload(client, bob_token, bob_workspace)).status_code == 201  # свой лимит у Боба
    assert (await _upload(client, alice_token, alice_workspace)).status_code == 402


@pytest.mark.asyncio
async def test_web_upload_shows_limit_message(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_documents_per_user", 1)
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "Quota ws"})
    workspace = await _get_workspace_by_name("Quota ws")
    url = f"/web/workspaces/{workspace.id}/documents"

    first = await client.post(url, files={"file": ("a.txt", b"hello", "text/plain")})
    second = await client.post(url, files={"file": ("b.txt", b"hello", "text/plain")})

    assert first.status_code == 200
    assert second.status_code == 200  # htmx получает партиал со ошибкой, не HTTP-ошибку
    assert "лимит" in second.text.lower()


# --- Дневной лимит вопросов ---


@pytest.mark.asyncio
async def test_daily_question_limit_blocks_extra_questions(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_question_limit", 2)
    _patch_providers(monkeypatch)
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    assert (await _ask(client, token, workspace_id)).status_code == 200
    assert (await _ask(client, token, workspace_id)).status_code == 200

    response = await _ask(client, token, workspace_id)

    assert response.status_code == 402
    assert "лимит" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_yesterdays_questions_do_not_count(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_question_limit", 1)
    _patch_providers(monkeypatch)
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    # Вопрос 25 часов назад — гарантированно до полуночи UTC сегодняшнего дня
    long_ago = datetime.now(UTC) - timedelta(hours=25)
    async with TestSessionLocal() as session:
        chat = Chat(workspace_id=uuid.UUID(workspace_id))
        session.add(chat)
        await session.flush()
        session.add(
            Message(
                chat_id=chat.id,
                role=MessageRole.USER,
                content="old question",
                created_at=long_ago,
            )
        )
        await session.commit()

    assert (await _ask(client, token, workspace_id)).status_code == 200  # вчерашний не считается
    assert (await _ask(client, token, workspace_id)).status_code == 402  # а сегодняшний — да


@pytest.mark.asyncio
async def test_rejected_question_does_not_create_empty_chat(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "daily_question_limit", 0)
    _patch_providers(monkeypatch)
    token = await _register_and_login(client, "alice@example.com")
    workspace_id = await _create_workspace(client, token)

    response = await _ask(client, token, workspace_id)
    assert response.status_code == 402

    async with TestSessionLocal() as session:
        result = await session.execute(
            select(Chat).where(Chat.workspace_id == uuid.UUID(workspace_id))
        )
        assert result.scalars().all() == []