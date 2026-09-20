import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.chunk_repository import ChunkRepository
from app.schemas.chat import SourceChunk
from app.services.embeddings import get_embedding_provider
from app.services.workspace_service import WorkspaceService


class ChatService:
    def __init__(self, db: AsyncSession):
        self.chunk_repo = ChunkRepository(db)
        self.workspace_service = WorkspaceService(db)

    async def search_relevant_chunks(
        self, workspace_id: uuid.UUID, owner_id: uuid.UUID, question: str, top_k: int = 5
    ) -> list[SourceChunk]:
        # Бросит WorkspaceNotFoundError, если workspace не существует или чужой —
        # роутер превратит это в 404
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)

        embedding_provider = get_embedding_provider()
        query_vector = await embedding_provider.embed_query(question)

        rows = await self.chunk_repo.search_similar(workspace_id, query_vector, top_k)

        return [
            SourceChunk(
                document_id=chunk.document_id,
                filename=filename,
                content=chunk.content,
                similarity=1 - distance,
            )
            for chunk, filename, distance in rows
        ]
