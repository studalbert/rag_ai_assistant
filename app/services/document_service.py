import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import FileStorage
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.services.workspace_service import WorkspaceService

# Разрешённые типы файлов на этом этапе — расширим при добавлении парсинга под каждый формат
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
}


class UnsupportedFileTypeError(Exception):
    pass


class FileTooLargeError(Exception):
    pass


class DocumentService:
    def __init__(self, db: AsyncSession, storage: FileStorage):
        self.repo = DocumentRepository(db)
        self.workspace_service = WorkspaceService(db)
        self.storage = storage

    async def upload_document(
        self,
        workspace_id: uuid.UUID,
        owner_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Document:
        # Бросит WorkspaceNotFoundError, если workspace не существует или не принадлежит owner_id —
        # роутер превратит это в 404, отдельно обрабатывать здесь не нужно
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)

        if content_type not in ALLOWED_CONTENT_TYPES:
            raise UnsupportedFileTypeError(f"Content type {content_type} is not supported")

        max_size_bytes = settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_size_bytes:
            raise FileTooLargeError(f"File exceeds {settings.max_upload_size_mb}MB limit")

        file_path = await self.storage.save(content, filename)

        return await self.repo.create(
            workspace_id=workspace_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
        )

    async def list_documents(self, workspace_id: uuid.UUID, owner_id: uuid.UUID) -> list[Document]:
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)
        return await self.repo.list_by_workspace(workspace_id)