import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk


class ChunkRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def bulk_create(
        self, document_id: uuid.UUID, texts: list[str], embeddings: list[list[float]]
    ) -> None:
        if len(texts) != len(embeddings):
            raise ValueError("texts and embeddings must have the same length")

        chunks = [
            Chunk(document_id=document_id, content=text, order_index=index, embedding=embedding)
            for index, (text, embedding) in enumerate(zip(texts, embeddings, strict=True))
        ]
        self.db.add_all(chunks)
        await self.db.commit()
