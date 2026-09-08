import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс — от него наследуются все модели."""

    pass


class TimestampMixin:
    """Подмешиваем created_at/updated_at туда, где это нужно (почти везде)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    """Фабрика для UUID-первичного ключа.

    Используем UUID, а не autoincrement int, чтобы ID нельзя было
    угадать перебором (важно, когда есть публичные ссылки на объекты).
    """
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
