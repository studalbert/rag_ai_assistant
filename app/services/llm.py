from collections.abc import AsyncIterator
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import settings


class LLMProvider(Protocol):
    def stream_completion(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Стримит ответ модели по частям — по одному фрагменту текста за раз."""
        ...


class YandexGPTProvider:
    """YandexGPT доступен через OpenAI-совместимый endpoint — переиспользуем
    официальный openai SDK, просто указывая другой base_url и специфичный
    формат URI модели вместо привычного 'gpt-4'/'gpt-3.5-turbo'."""

    def __init__(self, api_key: str, folder_id: str, model: str):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://llm.api.cloud.yandex.net/v1",
            project=folder_id,
        )
        self.model_uri = f"gpt://{folder_id}/{model}/latest"

    async def stream_completion(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model_uri,
            messages=messages,
            stream=True,
            temperature=0.2,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


def get_llm_provider() -> LLMProvider:
    """Фабрика — вынесена отдельно, чтобы в тестах можно было подменить
    на фейковую реализацию без реального обращения к Yandex Cloud."""
    return YandexGPTProvider(
        api_key=settings.yandex_api_key,
        folder_id=settings.yandex_folder_id,
        model=settings.yandex_gpt_model,
    )