from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "rag_assistant",
    broker=settings.redis_url,
    backend=settings.redis_url,  # храним результаты задач тоже в Redis — удобно для дебага
    include=["app.tasks.document_tasks"],  # где Celery искать задачи
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Задача не должна теряться, если воркер упал посреди выполнения —
    # Celery повторно отдаст её другому воркеру
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Явно фиксируем поведение retry на старте — в Celery 6.0 дефолт меняется,
    # лучше не зависеть от того, что "было по умолчанию раньше"
    broker_connection_retry_on_startup=True,
)
