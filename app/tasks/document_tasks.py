import asyncio
import uuid

from app.core.celery_app import celery_app


async def _process_document_async(document_id: uuid.UUID) -> str:
    # Здесь на следующем шаге появится реальная логика:
    # извлечение текста -> чанкинг -> эмбеддинги -> сохранение в БД
    return f"processed document {document_id}"


@celery_app.task(name="process_document")
def process_document(document_id: str) -> str:
    """Точка входа для Celery. Сама задача — синхронная функция (так требует Celery),
    но внутри неё мы уходим в asyncio.run(), чтобы переиспользовать async-код
    (SQLAlchemy async engine, репозитории и т.д.) без дублирования на sync-версию."""
    return asyncio.run(_process_document_async(uuid.UUID(document_id)))

