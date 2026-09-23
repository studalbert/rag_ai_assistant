from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import InvalidTokenError, TokenType, decode_token
from app.models.user import User
from app.repositories.user_repository import UserRepository

ACCESS_TOKEN_COOKIE = "access_token"


def _redirect_to_login() -> HTTPException:
    # 303 See Other + Location — браузер сам сделает редирект, даже если тело
    # ответа не HTML. Это стандартный приём для "требуется логин" в серверном вебе.
    return HTTPException(
        status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/web/login"}
    )


async def get_current_web_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if token is None:
        raise _redirect_to_login()

    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise _redirect_to_login() from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise _redirect_to_login()

    return user