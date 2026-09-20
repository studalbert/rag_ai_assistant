import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, Message
from app.models.enums import MessageRole


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
