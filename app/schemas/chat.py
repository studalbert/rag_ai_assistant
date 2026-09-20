import uuid
 
from pydantic import BaseModel
 
 
class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    # None -> создать новый чат; иначе продолжить существующий (должен принадлежать
    # тому же workspace, иначе 404 — та же логика, что и с самим workspace)
    chat_id: uuid.UUID | None = None
 
 
class SourceChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    similarity: float  # 1 - cosine_distance; ближе к 1 — более релевантно
 
 
class AskResponse(BaseModel):
    # Промежуточный контракт — на следующем шаге сюда добавится сгенерированный
    # LLM ответ; пока возвращаем только найденные источники, чтобы можно было
    # проверить качество самого векторного поиска отдельно от генерации.
    sources: list[SourceChunk]
