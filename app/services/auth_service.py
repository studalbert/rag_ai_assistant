from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
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

        # Намеренно не различаем "юзера нет" и "пароль неверный" в тексте ошибки —
        # иначе можно перебором узнавать, какие email зарегистрированы (user enumeration)
        if user is None or user.hashed_password is None:
            raise InvalidCredentialsError("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentialsError("Invalid email or password")

        return user