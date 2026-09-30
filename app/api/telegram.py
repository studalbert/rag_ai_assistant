from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.telegram import TelegramLinkCodeResponse, TelegramLinkRequest
from app.schemas.token import TokenPair
from app.services.auth_service import AuthService
from app.services.telegram_link_service import (
    LINK_CODE_TTL_SECONDS,
    InvalidLinkCodeError,
    TelegramLinkService,
)

router = APIRouter(prefix="/auth/telegram", tags=["telegram"])


@router.post("/link-code", response_model=TelegramLinkCodeResponse)
async def create_link_code(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TelegramLinkCodeResponse:
    service = TelegramLinkService(db)
    code = await service.generate_link_code(current_user.id)
    return TelegramLinkCodeResponse(code=code, expires_in_seconds=LINK_CODE_TTL_SECONDS)


@router.post("/link", response_model=TokenPair)
async def link_telegram_account(
    body: TelegramLinkRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Намеренно без авторизации: сам одноразовый код, выданный залогиненному
    пользователю в вебе, и есть доказательство личности на этом шаге."""
    service = TelegramLinkService(db)
    try:
        user = await service.consume_link_code(body.code, body.telegram_id)
    except InvalidLinkCodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AuthService(db).issue_tokens(user.id)