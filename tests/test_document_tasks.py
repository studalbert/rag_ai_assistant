import uuid

import pytest
from sqlalchemy import select

import app.tasks.document_tasks as document_tasks
from app.models.chunk import EMBEDDING_DIM, Chunk
from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.user import User
from app.models.workspace import Workspace
from tests.conftest import TestSessionLocal, test_engine


class FakeEmbeddingProvider:
    """Возвращает детерминированные векторы нужной размерности без реального инференса."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * EMBEDDING_DIM for _ in texts]


class FailingEmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("provider unavailable")


@pytest.fixture(autouse=True)
def _patch_task_infra(monkeypatch: pytest.MonkeyPatch) -> None:
    """Задача обрабатывает документы через свою собственную AsyncSessionLocal/engine
    (не через FastAPI dependency injection), поэтому обычный override_get_db
    её не затрагивает — подменяем эти имена прямо в модуле задачи."""
    monkeypatch.setattr(document_tasks, "AsyncSessionLocal", TestSessionLocal)
    monkeypatch.setattr(document_tasks, "engine", test_engine)
    monkeypatch.setattr(document_tasks, "get_embedding_provider", lambda: FakeEmbeddingProvider())


async def _create_document(
    content: bytes, content_type: str, tmp_path, filename: str = "doc.txt"
) -> uuid.UUID:
    """Создаёт User -> Workspace -> Document напрямую через тестовую сессию,
    без похода через HTTP API — нам нужен только сам факт существования записи."""
    async with TestSessionLocal() as session:
        user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
        session.add(user)
        await session.flush()

        workspace = Workspace(name="Test workspace", owner_id=user.id)
        session.add(workspace)
        await session.flush()

        file_path = tmp_path / filename
        file_path.write_bytes(content)

        document = Document(
            workspace_id=workspace.id,
            filename=filename,
            file_path=str(file_path),
            content_type=content_type,
            status=DocumentStatus.PENDING,
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        return document.id


@pytest.mark.asyncio
async def test_process_document_success_creates_chunks_and_marks_ready(tmp_path) -> None:
    document_id = await _create_document(b"hello world " * 200, "text/plain", tmp_path)

    await document_tasks._process_document_async(document_id)

    async with TestSessionLocal() as session:
        document = await session.get(Document, document_id)
        assert document.status == DocumentStatus.READY
        assert document.error_message is None

        result = await session.execute(select(Chunk).where(Chunk.document_id == document_id))
        chunks = result.scalars().all()
        assert len(chunks) > 0
        assert len(chunks[0].embedding) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_process_document_extraction_failure_marks_failed(tmp_path) -> None:
    invalid_utf8 = b"\xff\xfe\x00\x01"
    document_id = await _create_document(invalid_utf8, "text/plain", tmp_path)

    await document_tasks._process_document_async(document_id)

    async with TestSessionLocal() as session:
        document = await session.get(Document, document_id)
        assert document.status == DocumentStatus.FAILED
        assert document.error_message is not None

        result = await session.execute(select(Chunk).where(Chunk.document_id == document_id))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_process_document_embedding_failure_marks_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        document_tasks, "get_embedding_provider", lambda: FailingEmbeddingProvider()
    )
    document_id = await _create_document(b"hello world", "text/plain", tmp_path)

    await document_tasks._process_document_async(document_id)

    async with TestSessionLocal() as session:
        document = await session.get(Document, document_id)
        assert document.status == DocumentStatus.FAILED
        assert "Embedding generation failed" in document.error_message


@pytest.mark.asyncio
async def test_process_document_missing_document_is_noop() -> None:
    # Документ мог быть удалён между постановкой задачи в очередь и её выполнением —
    # задача не должна падать с ошибкой в этом случае
    await document_tasks._process_document_async(uuid.uuid4())
