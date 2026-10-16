import json
import uuid
from collections.abc import AsyncIterator

from app.schemas.chat import SourceChunk
from app.services.chat_service import ChatService
from app.services.llm import (
    LLMProvider,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_ask_response(
    llm_provider: LLMProvider,
    service: ChatService,
    chat_id: uuid.UUID,
    question: str,
    sources: list[SourceChunk],
    messages: list[dict[str, str]],
) -> AsyncIterator[str]:
    """Общая механика стрима для JSON API (/ask/stream) и веб-интерфейса —
    провайдера получает вызывающий роутер сам (так проще подменять его в тестах
    через monkeypatch конкретно того модуля, откуда он вызван)."""
    yield sse({"type": "chat_id", "chat_id": str(chat_id)})
    yield sse(
        {
            "type": "sources",
            "sources": [source.model_dump(mode="json") for source in sources],
        }
    )

    answer_parts: list[str] = []
    try:
        async for token in llm_provider.stream_completion(messages):
            answer_parts.append(token)
            yield sse({"type": "token", "content": token})
    except (LLMTimeoutError, LLMRateLimitError, LLMUnavailableError) as exc:
        # Понятное сообщение для UI; неполный ответ в историю не пишем
        yield sse({"type": "error", "message": str(exc)})
        return
    except Exception:
        yield sse({"type": "error", "message": "LLM provider error. Please try again."})
        return

    full_answer = "".join(answer_parts)
    source_chunk_ids = [source.chunk_id for source in sources]
    await service.save_exchange(chat_id, question, full_answer, source_chunk_ids)

    yield sse({"type": "done"})
