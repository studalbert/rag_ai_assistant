import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.enums import DocumentStatus
from app.models.workspace import Workspace


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        workspace_id: uuid.UUID,
        filename: str,
        file_path: str,
        content_type: str,
    ) -> Document:
        document = Document(
            workspace_id=workspace_id,
            filename=filename,
            file_path=file_path,
            content_type=content_type,
            status=DocumentStatus.PENDING,
        )
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def list_by_workspace(self, workspace_id: uuid.UUID) -> list[Document]:
        result = await self.db.execute(
            select(Document)
            .where(Document.workspace_id == workspace_id)
            .order_by(Document.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, document_id: uuid.UUID) -> Document | None:
        return await self.db.get(Document, document_id)

    async def count_by_owner(self, owner_id: uuid.UUID) -> int:
        """Всего документов пользователя во всех его workspace."""
        result = await self.db.execute(
            select(func.count(Document.id))
            .join(Workspace, Document.workspace_id == Workspace.id)
            .where(Workspace.owner_id == owner_id)
        )
        return result.scalar_one()
