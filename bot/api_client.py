import httpx

from bot import storage
from bot.config import settings


class LinkError(Exception):
    pass


class NotLinkedError(Exception):
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
