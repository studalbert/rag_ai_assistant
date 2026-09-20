import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

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


class ChatService:
    def __init__(self, db: AsyncSession):
        self.chunk_repo = ChunkRepository(db)
        self.workspace_service = WorkspaceService(db)

    async def search_relevant_chunks(
        self, workspace_id: uuid.UUID, owner_id: uuid.UUID, question: str, top_k: int = 5
    ) -> list[SourceChunk]:
        # Бросит WorkspaceNotFoundError, если workspace не существует или чужой —
        # роутер превратит это в 404
        await self.workspace_service.get_owned_workspace(workspace_id, owner_id)

        embedding_provider = get_embedding_provider()
        query_vector = await embedding_provider.embed_query(question)

        rows = await self.chunk_repo.search_similar(workspace_id, query_vector, top_k)

        return [
            SourceChunk(
                document_id=chunk.document_id,
                filename=filename,
                content=chunk.content,
                similarity=1 - distance,
            )
            for chunk, filename, distance in rows
        ]

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

    async def prepare_ask(
        self, workspace_id: uuid.UUID, owner_id: uuid.UUID, question: str, top_k: int = 5
    ) -> tuple[list[SourceChunk], list[dict[str, str]]]:
        """Всё, что можно сделать ДО начала стриминга: проверка владения workspace,
        векторный поиск и сборка промпта. Вынесено отдельно от самого стриминга,
        чтобы ошибка (например, чужой workspace) вернулась нормальным HTTP-статусом,
        а не оборвала уже начавшийся SSE-поток на середине."""
        sources = await self.search_relevant_chunks(workspace_id, owner_id, question, top_k)
        messages = self.build_prompt(question, sources)
        return sources, messages
