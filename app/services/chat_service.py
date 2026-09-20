import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MessageRole
from app.repositories.chat_repository import ChatRepository
from app.repositories.chunk_repository import ChunkRepository
from app.schemas.chat import SourceChunk
from app.services.embeddings import get_embedding_provider
from app.services.workspace_service import WorkspaceService

SYSTEM_PROMPT = (
    "Ты — ассистент, отвечающий на вопросы строго на основе предоставленных "
    "фрагментов документов пользователя. Отвечай на языке вопроса. Если ответа "
    "нет в приведённом контексте — честно скажи, что не можешь найти ответ в "
    "загруженных документах, и не придумывай факты. При использовании фрагмента "
    "ссылайся на его номер в квадратных скобках, например [1]."
)


class ChatNotFoundError(Exception):
    """Тот же принцип, что и с WorkspaceNotFoundError: чужой или несуществующий
    чат снаружи выглядит одинаково — 404, без утечки самого факта существования."""
    pass


class ChatService:
    def __init__(self, db: AsyncSession):
        self.chunk_repo = ChunkRepository(db)
        self.chat_repo = ChatRepository(db)
        self.workspace_service = WorkspaceService(db)

    async def _search(
        self, workspace_id: uuid.UUID, question: str, top_k: int
    ) -> list[SourceChunk]:
        embedding_provider = get_embedding_provider()
        query_vector = await embedding_provider.embed_query(question)
        rows = await self.chunk_repo.search_similar(workspace_id, query_vector, top_k)

        return [
            SourceChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                content=chunk.content,
                similarity=1 - distance,
            )
            for chunk, filename, distance in rows
        ]

    async def search_relevant_chunks(
        self, workspace_id: uuid.UUID, owner_id: uuid.UUID, question: str, top_k: int = 5
    ) -> list[SourceChunk]:
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)
        return await self._search(workspace_id, question, top_k)

    def build_prompt(self, question: str, sources: Sequence[SourceChunk]) -> list[dict[str, str]]:
        if not sources:
            context = "(в базе знаний не нашлось релевантных фрагментов)"
        else:
            context = "\n\n".join(
                f"[{index}] Источник: {source.filename}\n{source.content}"
                for index, source in enumerate(sources, start=1)
            )

        user_content = f"Контекст из документов:\n{context}\n\nВопрос пользователя: {question}"

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    async def _get_or_create_chat(
        self, workspace_id: uuid.UUID, chat_id: uuid.UUID | None
    ) -> uuid.UUID:
        if chat_id is None:
            chat = await self.chat_repo.create(workspace_id)
            return chat.id

        chat = await self.chat_repo.get_by_id(chat_id)
        if chat is None or chat.workspace_id != workspace_id:
            raise ChatNotFoundError(f"Chat {chat_id} not found")
        return chat.id

    async def prepare_ask(
        self,
        workspace_id: uuid.UUID,
        owner_id: uuid.UUID,
        question: str,
        top_k: int = 5,
        chat_id: uuid.UUID | None = None,
    ) -> tuple[uuid.UUID, list[SourceChunk], list[dict[str, str]]]:
        """Всё, что можно сделать ДО начала стриминга: проверка владения workspace
        и чатом, векторный поиск, сборка промпта. См. комментарий в роутере о том,
        почему это отделено от самого стриминга."""
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)
        resolved_chat_id = await self._get_or_create_chat(workspace_id, chat_id)
        sources = await self._search(workspace_id, question, top_k)
        messages = self.build_prompt(question, sources)
        return resolved_chat_id, sources, messages

    async def save_exchange(
        self,
        chat_id: uuid.UUID,
        question: str,
        answer: str,
        source_chunk_ids: Sequence[uuid.UUID],
    ) -> None:
        await self.chat_repo.add_message(chat_id, MessageRole.USER, question)
        await self.chat_repo.add_message(
            chat_id,
            MessageRole.ASSISTANT,
            answer,
            source_chunk_ids=list(source_chunk_ids) or None,
        )
