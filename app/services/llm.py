import asyncio
import random
from collections.abc import AsyncIterator
from typing import Protocol

import openai
from openai import AsyncOpenAI

from app.core.config import settings


class LLMTimeoutError(Exception):
    """Провайдер не ответил вовремя."""


class LLMRateLimitError(Exception):
    """Провайдер вернул 429 / quota exceeded."""


class LLMUnavailableError(Exception):
    """Временная недоступность или исчерпаны ретраи."""


class LLMProvider(Protocol):
    def stream_completion(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        """Стримит ответ модели по частям — по одному фрагменту текста за раз."""
        ...


def _is_retryable(exc: BaseException) -> bool:
    """Временные сбои, которые имеет смысл повторить."""
    return isinstance(
        exc,
        (
            openai.APITimeoutError,
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.InternalServerError,
        ),
    )


def _map_openai_error(exc: BaseException) -> Exception:
    """Переводим ошибки SDK в свои — чтобы остальной код не зависел от openai.*."""
    if isinstance(exc, openai.APITimeoutError):
        return LLMTimeoutError("LLM request timed out. Please try again.")
    if isinstance(exc, openai.RateLimitError):
        return LLMRateLimitError("LLM rate limit exceeded. Please try again later.")
    if isinstance(exc, (openai.APIConnectionError, openai.InternalServerError)):
        return LLMUnavailableError("LLM provider is temporarily unavailable.")
    return LLMUnavailableError(f"LLM provider error: {exc}")


class YandexGPTProvider:
    """YandexGPT через OpenAI-совместимый endpoint + timeout/retry на старте стрима."""

    def __init__(self, api_key: str, folder_id: str, model: str):
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://llm.api.cloud.yandex.net/v1",
            project=folder_id,
            timeout=settings.llm_timeout_seconds,
        )
        self.model_uri = f"gpt://{folder_id}/{model}/latest"

    async def stream_completion(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        max_retries = settings.llm_max_retries
        base_delay = settings.llm_retry_base_delay

        for attempt in range(max_retries + 1):
            started_yielding = False
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model_uri,
                    messages=messages,
                    stream=True,
                    temperature=0.2,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        started_yielding = True
                        yield delta
                return  # успешный стрим до конца

            except Exception as exc:
                # Уже отдали часть ответа клиенту — ретраить нельзя
                if started_yielding:
                    raise _map_openai_error(exc) from exc

                if not _is_retryable(exc) or attempt >= max_retries:
                    raise _map_openai_error(exc) from exc

                # exponential backoff + небольшой jitter
                delay = base_delay * (2**attempt) + random.uniform(0, 0.3)
                await asyncio.sleep(delay)


def get_llm_provider() -> LLMProvider:
    """Фабрика — в тестах подменяется без реального вызова Yandex Cloud."""
    return YandexGPTProvider(
        api_key=settings.yandex_api_key,
        folder_id=settings.yandex_folder_id,
        model=settings.yandex_gpt_model,
    )
