from pydantic import BaseModel


class TelegramLinkCodeResponse(BaseModel):
    code: str
    expires_in_seconds: int


class TelegramLinkRequest(BaseModel):
    code: str
    telegram_id: int