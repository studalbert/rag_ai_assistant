import uuid

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document


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

    async def search_similar(
        self, workspace_id: uuid.UUID, query_embedding: list[float], top_k: int
    ) -> list[Row]:
        """Топ-k чанков по косинусному расстоянию, отфильтрованных по workspace.

        cosine_distance возвращает 0 для идентичных векторов и 2 для противоположных —
        чем меньше, тем более похожи. Сортируем по возрастанию расстояния (ASC),
        т.е. самые похожие идут первыми.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding)

        result = await self.db.execute(
            select(Chunk, Document.filename, distance.label("distance"))
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.workspace_id == workspace_id)
            .order_by(distance)
            .limit(top_k)
        )
        return list(result.all())

