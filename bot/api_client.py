import json
from collections.abc import AsyncIterator

import httpx

from bot import storage
from bot.config import settings


class LinkError(Exception):
    pass


class NotLinkedError(Exception):
    pass


class AskError(Exception):
    pass


async def link_account(code: str, telegram_id: int) -> None:
    async with httpx.AsyncClient(base_url=settings.backend_api_base_url) as client:
        response = await client.post(
            "/auth/telegram/link", json={"code": code, "telegram_id": telegram_id}
        )

    if response.status_code != 200:
        detail = response.json().get("detail", "Не удалось привязать аккаунт")
        raise LinkError(detail)

    tokens = response.json()
    await storage.save_link(telegram_id, tokens["refresh_token"])


async def get_access_token(telegram_id: int) -> str:
    """Возвращает свежий access-токен, обновляя его через refresh-токен при
    каждом вызове. Токены короткоживущие (15 минут) — проще всегда обновлять
    перед обращением к API, чем городить отдельную проверку истечения."""
    refresh_token = await storage.get_refresh_token(telegram_id)
    if refresh_token is None:
        raise NotLinkedError("Аккаунт не привязан — используйте /link <код>")

    async with httpx.AsyncClient(base_url=settings.backend_api_base_url) as client:
        response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    if response.status_code != 200:
        raise NotLinkedError("Сессия истекла, привяжите аккаунт заново через /link <код>")

    tokens = response.json()
    # Сервер делает token rotation — сохраняем новый refresh_token, иначе он
    # станет невалидным, когда срок старого истечёт естественным путём
    await storage.update_refresh_token(telegram_id, tokens["refresh_token"])
    return tokens["access_token"]


async def list_workspaces(telegram_id: int) -> list[dict]:
    access_token = await get_access_token(telegram_id)
    async with httpx.AsyncClient(base_url=settings.backend_api_base_url) as client:
        response = await client.get(
            "/workspaces", headers={"Authorization": f"Bearer {access_token}"}
        )
    response.raise_for_status()
    return response.json()


async def ask_stream(
    telegram_id: int, workspace_id: str, question: str, chat_id: str | None
) -> AsyncIterator[dict]:
    """Дёргает тот же /ask/stream, что и веб-интерфейс, и разбирает те же
    SSE-события (chat_id/sources/token/error/done) — никакой отдельной логики
    на backend для бота не существует, это буквально тот же эндпоинт."""
    access_token = await get_access_token(telegram_id)

    async with httpx.AsyncClient(base_url=settings.backend_api_base_url, timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"/workspaces/{workspace_id}/ask/stream",
            json={"question": question, "chat_id": chat_id},
            headers={"Authorization": f"Bearer {access_token}"},
        ) as response:
            if response.status_code != 200:
                raise AskError(f"Backend returned {response.status_code}")

            buffer = ""
            async for text_chunk in response.aiter_text():
                buffer += text_chunk
                while "\n\n" in buffer:
                    part, buffer = buffer.split("\n\n", 1)
                    for line in part.splitlines():
                        if line.startswith("data: "):
                            yield json.loads(line.removeprefix("data: "))
