import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.document import Document

# Размерность эмбеддинга зависит от модели:
# intfloat/multilingual-e5-base (наша локальная модель) -> 768
# Зафиксируй значение под свою модель ДО первой миграции — поменять потом сложнее.
EMBEDDING_DIM = 768


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = uuid_pk()
    content: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer)  # позиция чанка внутри документа

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document: Mapped["Document"] = relationship(back_populates="chunks")
