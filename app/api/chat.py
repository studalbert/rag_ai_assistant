import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.chat import AskRequest, AskResponse
from app.services.chat_service import ChatService
from app.services.llm import get_llm_provider
from app.services.workspace_service import WorkspaceNotFoundError

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["chat"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    workspace_id: uuid.UUID,
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AskResponse:
    service = ChatService(db)
    try:
        sources = await service.search_relevant_chunks(
            workspace_id, current_user.id, body.question, body.top_k
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AskResponse(sources=sources)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/ask/stream")
async def ask_stream(
    workspace_id: uuid.UUID,
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)
    try:
        sources, messages = await service.prepare_ask(
            workspace_id, current_user.id, body.question, body.top_k
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    async def event_generator() -> AsyncIterator[str]:
        yield _sse(
            {
                "type": "sources",
                "sources": [source.model_dump(mode="json") for source in sources],
            }
        )

        llm_provider = get_llm_provider()
        async for token in llm_provider.stream_completion(messages):
            yield _sse({"type": "token", "content": token})

        yield _sse({"type": "done"})

    return StreamingResponse(event_generator(), media_type="text/event-stream")
