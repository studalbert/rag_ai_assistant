import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.token import TokenPair
from app.schemas.user import UserCreate


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def register(self, user_data: UserCreate) -> User:
        existing = await self.repo.get_by_email(user_data.email)
        if existing is not None:
            raise EmailAlreadyRegisteredError(f"Email {user_data.email} already registered")

        hashed = hash_password(user_data.password)
        return await self.repo.create(user_data, hashed)

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.repo.get_by_email(email)

        if user is None or user.hashed_password is None:
            raise InvalidCredentialsError("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid email or password")

        return user

    def issue_tokens(self, user_id: uuid.UUID) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user_id),
            refresh_token=create_refresh_token(user_id),
        )

    async def refresh_tokens(self, refresh_token: str) -> TokenPair:
        try:
            user_id = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise InvalidCredentialsError("Invalid or expired refresh token") from exc

        user = await self.repo.get_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidCredentialsError("User no longer exists or is inactive")

        # Выдаём полностью новую пару — включая новый refresh-токен (token rotation).
        # Это лучше, чем переиспользовать старый refresh: если его украдут, у него
        # всё равно ограниченный срок жизни от момента последнего использования.
        return self.issue_tokens(user.id)
