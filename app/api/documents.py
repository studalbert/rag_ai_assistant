import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_storage
from app.core.db import get_db
from app.core.storage import FileStorage
from app.models.user import User
from app.schemas.document import DocumentRead
from app.services.document_service import (
    DocumentService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.services.workspace_service import WorkspaceNotFoundError

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> DocumentRead:
    service = DocumentService(db, storage)
    content = await file.read()

    try:
        document = await service.upload_document(
            workspace_id=workspace_id,
            owner_id=current_user.id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc

    return DocumentRead.model_validate(document)


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> list[DocumentRead]:
    service = DocumentService(db, storage)
    try:
        documents = await service.list_documents(workspace_id, current_user.id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [DocumentRead.model_validate(d) for d in documents]
