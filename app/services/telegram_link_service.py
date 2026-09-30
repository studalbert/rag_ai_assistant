import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import redis_client
from app.models.user import User
from app.repositories.user_repository import UserRepository

LINK_CODE_TTL_SECONDS = 600  # 10 минут — код одноразовый и живёт недолго
LINK_CODE_PREFIX = "telegram_link:"


class InvalidLinkCodeError(Exception):
    pass


class TelegramLinkService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def generate_link_code(self, user_id: uuid.UUID) -> str:
        # token_hex(4) -> 8 символов, для короткоживущего одноразового кода достаточно
        code = secrets.token_hex(4)
        await redis_client.set(f"{LINK_CODE_PREFIX}{code}", str(user_id), ex=LINK_CODE_TTL_SECONDS)
        return code

    async def consume_link_code(self, code: str, telegram_id: int) -> User:
        key = f"{LINK_CODE_PREFIX}{code}"
        user_id_str = await redis_client.get(key)
        if user_id_str is None:
            raise InvalidLinkCodeError("Code is invalid or expired")

        # Удаляем сразу после чтения — код одноразовый, повторное использование
        # (даже той же строки) не должно срабатывать снова
        await redis_client.delete(key)

        user = await self.user_repo.get_by_id(uuid.UUID(user_id_str))
        if user is None:
            raise InvalidLinkCodeError("User no longer exists")

        existing = await self.user_repo.get_by_telegram_id(telegram_id)
        if existing is not None and existing.id != user.id:
            raise InvalidLinkCodeError(
                "This Telegram account is already linked to a different user"
            )

        user.telegram_id = telegram_id
        await self.db.commit()
        await self.db.refresh(user)
        return user
