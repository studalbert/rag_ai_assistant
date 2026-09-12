import asyncio
import uuid

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.storage import LocalFileStorage
from app.models.enums import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.services.text_extraction import TextExtractionError, extract_text


async def _process_document_async(document_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        repo = DocumentRepository(db)
        document = await repo.get_by_id(document_id)

        if document is None:
            # Документ мог быть удалён между постановкой задачи в очередь и её выполнением —
            # не ошибка воркера, просто нечего обрабатывать
            return

        document.status = DocumentStatus.PROCESSING
        await db.commit()

        storage = LocalFileStorage(base_dir=settings.upload_dir)

        try:
            content = await storage.read(document.file_path)
            text = extract_text(content, document.content_type)
        except (TextExtractionError, OSError) as exc:
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)
            await db.commit()
            return

        # На следующем шаге здесь появится: чанкинг -> эмбеддинги -> сохранение чанков ->
        # только после этого статус меняется на READY. Пока просто подтверждаем,
        # что текст успешно извлёкся (длина видна в логах воркера).
        print(f"Extracted {len(text)} characters from document {document_id}")  # noqa: T201


@celery_app.task(name="process_document")
def process_document(document_id: str) -> None:
    """Точка входа для Celery. Сама задача — синхронная функция (так требует Celery),
    но внутри неё мы уходим в asyncio.run(), чтобы переиспользовать async-код
    (SQLAlchemy async engine, репозитории и т.д.) без дублирования на sync-версию."""
    asyncio.run(_process_document_async(uuid.UUID(document_id)))
