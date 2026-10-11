import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, Message
from app.models.enums import MessageRole
from app.models.workspace import Workspace


class ChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, workspace_id: uuid.UUID) -> Chat:
        chat = Chat(workspace_id=workspace_id)
        self.db.add(chat)
        await self.db.commit()
        await self.db.refresh(chat)
        return chat

    async def get_by_id(self, chat_id: uuid.UUID) -> Chat | None:
        return await self.db.get(Chat, chat_id)

    async def add_message(
        self,
        chat_id: uuid.UUID,
        role: MessageRole,
        content: str,
        source_chunk_ids: list[uuid.UUID] | None = None,
    ) -> Message:
        message = Message(
            chat_id=chat_id, role=role, content=content, source_chunk_ids=source_chunk_ids
        )
        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def count_user_questions_since(self, owner_id: uuid.UUID, since: datetime) -> int:
        """Сколько вопросов (сообщений с role=user) задал пользователь во всех
        своих workspace начиная с момента `since`."""
        result = await self.db.execute(
            select(func.count(Message.id))
            .join(Chat, Message.chat_id == Chat.id)
            .join(Workspace, Chat.workspace_id == Workspace.id)
            .where(
                Workspace.owner_id == owner_id,
                Message.role == MessageRole.USER,
                Message.created_at >= since,
            )
        )
        return result.scalar_one()
