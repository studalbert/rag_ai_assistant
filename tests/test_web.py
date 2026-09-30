import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.services.chat_service as chat_service_module
import app.web.routes as web_routes_module
from app.models.chat import Message
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.user import User
from app.models.workspace import Workspace
from tests.conftest import TestSessionLocal
from tests.test_chat import FakeLLMProvider, FakeQueryEmbeddingProvider, _parse_sse, _unit_vector


async def _register_web(client: AsyncClient, email: str, password: str = "secret123"):
    return await client.post("/web/register", data={"email": email, "password": password})


async def _login_web(client: AsyncClient, email: str, password: str = "secret123"):
    return await client.post("/web/login", data={"email": email, "password": password})


async def _get_workspace_by_name(name: str) -> Workspace:
    async with TestSessionLocal() as session:
        result = await session.execute(select(Workspace).where(Workspace.name == name))
        return result.scalar_one()


async def _create_foreign_workspace(owner_email: str, workspace_name: str) -> Workspace:
    """Создаёт пользователя и его workspace напрямую в БД — имитирует 'чужие' данные,
    к которым у клиента (авторизованного как другой пользователь) не должно быть доступа."""
    async with TestSessionLocal() as session:
        owner = User(email=owner_email, hashed_password="x")
        session.add(owner)
        await session.flush()

        workspace = Workspace(name=workspace_name, owner_id=owner.id)
        session.add(workspace)
        await session.commit()
        await session.refresh(workspace)
        return workspace


# --- Авторизация ---


@pytest.mark.asyncio
async def test_login_page_renders(client: AsyncClient) -> None:
    response = await client.get("/web/login")
    assert response.status_code == 200
    assert "<form" in response.text


@pytest.mark.asyncio
async def test_register_page_renders(client: AsyncClient) -> None:
    response = await client.get("/web/register")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_root_redirects_to_login(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.headers["location"] == "/web/login"


@pytest.mark.asyncio
async def test_register_web_sets_cookie_and_redirects(client: AsyncClient) -> None:
    response = await _register_web(client, "alice@example.com")

    assert response.status_code == 303
    assert response.headers["location"] == "/web/workspaces"
    assert "access_token" in response.cookies


@pytest.mark.asyncio
async def test_register_web_duplicate_email_shows_error(client: AsyncClient) -> None:
    await _register_web(client, "bob@example.com")
    response = await _register_web(client, "bob@example.com")

    assert response.status_code == 409
    assert "уже зарегистрирован" in response.text


@pytest.mark.asyncio
async def test_login_web_correct_credentials_redirects(client: AsyncClient) -> None:
    await _register_web(client, "carol@example.com")
    response = await _login_web(client, "carol@example.com")

    assert response.status_code == 303
    assert response.headers["location"] == "/web/workspaces"


@pytest.mark.asyncio
async def test_login_web_wrong_password_shows_error(client: AsyncClient) -> None:
    await _register_web(client, "dave@example.com")
    response = await client.post(
        "/web/login", data={"email": "dave@example.com", "password": "wrong"}
    )

    assert response.status_code == 401
    assert "Неверный" in response.text


@pytest.mark.asyncio
async def test_workspaces_page_without_cookie_redirects_to_login(client: AsyncClient) -> None:
    response = await client.get("/web/workspaces")

    assert response.status_code == 303
    assert response.headers["location"] == "/web/login"


@pytest.mark.asyncio
async def test_logout_clears_cookie(client: AsyncClient) -> None:
    await _register_web(client, "erin@example.com")

    logout_response = await client.get("/web/logout")
    assert logout_response.status_code == 303
    assert logout_response.headers["location"] == "/web/login"

    protected_response = await client.get("/web/workspaces")
    assert protected_response.status_code == 303
    assert protected_response.headers["location"] == "/web/login"


# --- Workspaces ---


@pytest.mark.asyncio
async def test_create_workspace_web_returns_updated_list(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")

    response = await client.post("/web/workspaces", data={"name": "My workspace"})

    assert response.status_code == 200
    assert "My workspace" in response.text
    assert 'id="workspace-list"' in response.text


@pytest.mark.asyncio
async def test_delete_own_workspace_web(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "To delete"})
    workspace = await _get_workspace_by_name("To delete")

    response = await client.delete(f"/web/workspaces/{workspace.id}")

    assert response.status_code == 200
    assert response.text == ""


@pytest.mark.asyncio
async def test_delete_foreign_workspace_web_is_silently_ignored(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    foreign_workspace = await _create_foreign_workspace("bob@example.com", "Bob's workspace")

    response = await client.delete(f"/web/workspaces/{foreign_workspace.id}")

    assert response.status_code == 200  # тихо ничего не делает — не 403/404, не падает

    async with TestSessionLocal() as session:
        still_exists = await session.get(Workspace, foreign_workspace.id)
    assert still_exists is not None


@pytest.mark.asyncio
async def test_workspace_detail_page_requires_ownership(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    foreign_workspace = await _create_foreign_workspace("bob2@example.com", "Bob's private")

    response = await client.get(f"/web/workspaces/{foreign_workspace.id}")

    assert response.status_code == 303
    assert response.headers["location"] == "/web/workspaces"


# --- Документы ---


@pytest.mark.asyncio
async def test_upload_document_web_shows_pending_status(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "Docs workspace"})
    workspace = await _get_workspace_by_name("Docs workspace")

    response = await client.post(
        f"/web/workspaces/{workspace.id}/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert "notes.txt" in response.text
    assert "pending" in response.text


@pytest.mark.asyncio
async def test_documents_list_partial_polling_endpoint(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "Poll workspace"})
    workspace = await _get_workspace_by_name("Poll workspace")

    response = await client.get(f"/web/workspaces/{workspace.id}/documents/list")

    assert response.status_code == 200
    assert 'id="document-list"' in response.text


@pytest.mark.asyncio
async def test_download_document_web_returns_file_content(
    client: AsyncClient, tmp_path
) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "DL workspace"})
    workspace = await _get_workspace_by_name("DL workspace")

    file_path = tmp_path / "source.txt"
    file_path.write_bytes(b"raw file content")

    async with TestSessionLocal() as session:
        document = Document(
            workspace_id=workspace.id,
            filename="source.txt",
            file_path=str(file_path),
            content_type="text/plain",
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

    response = await client.get(
        f"/web/workspaces/{workspace.id}/documents/{document.id}/download"
    )

    assert response.status_code == 200
    assert response.content == b"raw file content"
    assert response.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_download_document_from_wrong_workspace_returns_404(
    client: AsyncClient, tmp_path
) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "Alice ws"})
    alice_workspace = await _get_workspace_by_name("Alice ws")

    foreign_workspace = await _create_foreign_workspace("bob3@example.com", "Bob ws")
    file_path = tmp_path / "bob.txt"
    file_path.write_bytes(b"secret")

    async with TestSessionLocal() as session:
        document = Document(
            workspace_id=foreign_workspace.id,
            filename="bob.txt",
            file_path=str(file_path),
            content_type="text/plain",
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

    # Алиса подставляет СВОЙ workspace_id в URL с чужим document_id — тоже должно быть 404
    response = await client.get(
        f"/web/workspaces/{alice_workspace.id}/documents/{document.id}/download"
    )
    assert response.status_code == 404


# --- Чат ---


@pytest.mark.asyncio
async def test_chat_page_renders_for_owner(client: AsyncClient) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "Chat ws"})
    workspace = await _get_workspace_by_name("Chat ws")

    response = await client.get(f"/web/workspaces/{workspace.id}/chat")

    assert response.status_code == 200
    assert "ask-form" in response.text


@pytest.mark.asyncio
async def test_ask_stream_web_saves_history(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register_web(client, "alice@example.com")
    await client.post("/web/workspaces", data={"name": "RAG ws"})
    workspace = await _get_workspace_by_name("RAG ws")

    vector = _unit_vector(seed=1.0)
    async with TestSessionLocal() as session:
        document = Document(
            workspace_id=workspace.id,
            filename="doc.txt",
            file_path="/dev/null",
            content_type="text/plain",
            status=DocumentStatus.READY,
        )
        session.add(document)
        await session.flush()

        chunk = Chunk(document_id=document.id, content="Some content", order_index=0, embedding=vector)
        session.add(chunk)
        await session.commit()

    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(
        web_routes_module, "get_llm_provider", lambda: FakeLLMProvider(["Hi", " there"])
    )

    response = await client.post(
        f"/web/workspaces/{workspace.id}/ask/stream",
        json={"question": "test question"},
    )

    assert response.status_code == 200
    events = _parse_sse(response.text)
    tokens = [event["content"] for event in events if event["type"] == "token"]
    assert "".join(tokens) == "Hi there"

    chat_id = uuid.UUID(events[0]["chat_id"])
    async with TestSessionLocal() as session:
        result = await session.execute(select(Message).where(Message.chat_id == chat_id))
        messages = result.scalars().all()
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_ask_stream_web_on_foreign_workspace_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _register_web(client, "alice@example.com")
    foreign_workspace = await _create_foreign_workspace("bob4@example.com", "Bob's RAG ws")

    vector = _unit_vector(seed=1.0)
    monkeypatch.setattr(
        chat_service_module, "get_embedding_provider", lambda: FakeQueryEmbeddingProvider(vector)
    )
    monkeypatch.setattr(web_routes_module, "get_llm_provider", lambda: FakeLLMProvider(["x"]))

    response = await client.post(
        f"/web/workspaces/{foreign_workspace.id}/ask/stream",
        json={"question": "test"},
    )

    assert response.status_code == 404
