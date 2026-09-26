import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.chat import AskRequest, AskResponse
from app.services.chat_service import ChatNotFoundError, ChatService
from app.services.chat_streaming import stream_ask_response
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


@router.post("/ask/stream")
async def ask_stream(
    workspace_id: uuid.UUID,
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)
    try:
        chat_id, sources, messages = await service.prepare_ask(
            workspace_id, current_user.id, body.question, body.top_k, body.chat_id
        )
    except (WorkspaceNotFoundError, ChatNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    llm_provider = get_llm_provider()
    return StreamingResponse(
        stream_ask_response(llm_provider, service, chat_id, body.question, sources, messages),
        media_type="text/event-stream",
    )
