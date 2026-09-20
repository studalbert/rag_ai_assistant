import asyncio
from functools import lru_cache
from typing import Protocol

from sentence_transformers import SentenceTransformer

from app.core.config import settings


class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Возвращает по одному вектору на каждый текст документа, в том же порядке."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Возвращает вектор для поискового запроса (вопроса пользователя).

        Отдельный метод, а не просто embed([text])[0] — потому что у модели e5
        разные префиксы для документов и запросов, и смешивать их нельзя."""
        ...


@lru_cache(maxsize=1)
def _load_model(model_name: str) -> SentenceTransformer:
    # Кэшируем модель в памяти процесса — загрузка весов с диска (или скачивание
    # при первом запуске) занимает заметное время, повторять её на каждый вызов
    # задачи было бы неоправданно медленно
    return SentenceTransformer(model_name)


class LocalEmbeddingProvider:
    """Считает эмбеддинги локально на CPU через sentence-transformers,
    без обращения к каким-либо внешним API."""

    def __init__(self, model_name: str):
        self.model = _load_model(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Модель e5 обучена с конвенцией "passage: "/"query: " перед текстом —
        # без этого префикса качество ретрива заметно хуже. Для чанков документов
        # используем "passage: "; когда дойдём до поиска по вопросу пользователя,
        # тот текст нужно будет обернуть в "query: " — не забыть на будущем шаге.
        prefixed_texts = [f"passage: {text}" for text in texts]

        # model.encode — синхронный и CPU-тяжёлый вызов. Не await'им его напрямую,
        # иначе он заблокирует единственный поток event loop'а. asyncio.to_thread
        # уводит его в отдельный поток, освобождая event loop на время вычислений.
        embeddings = await asyncio.to_thread(
            self.model.encode, prefixed_texts, normalize_embeddings=True
        )
        return embeddings.tolist()

    async def embed_query(self, text: str) -> list[float]:
        prefixed_text = f"query: {text}"
        embedding = await asyncio.to_thread(
            self.model.encode, [prefixed_text], normalize_embeddings=True
        )
        return embedding[0].tolist()


def get_embedding_provider() -> EmbeddingProvider:
    """Фабрика — вынесена отдельно, чтобы в тестах можно было подменить
    (monkeypatch) на фейковую реализацию без реального инференса модели."""
    return LocalEmbeddingProvider(model_name=settings.embedding_model)
