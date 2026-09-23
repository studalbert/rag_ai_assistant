import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_storage
from app.core.db import get_db
from app.core.storage import FileStorage
from app.models.user import User
from app.schemas.user import UserCreate
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)
from app.services.document_service import (
    DocumentService,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.services.workspace_service import WorkspaceNotFoundError, WorkspaceService
from app.web.deps import ACCESS_TOKEN_COOKIE, get_current_web_user

router = APIRouter(prefix="/web", tags=["web"])
templates = Jinja2Templates(directory="app/templates")


# --- Авторизация ---


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    service = AuthService(db)
    try:
        user = await service.authenticate(email, password)
    except InvalidCredentialsError:
        return templates.TemplateResponse(
            request, "login.html", {"error": "Неверный email или пароль"}, status_code=401
        )

    tokens = service.issue_tokens(user.id)
    response = RedirectResponse(url="/web/workspaces", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(ACCESS_TOKEN_COOKIE, tokens.access_token, httponly=True, samesite="lax")
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "register.html", {})


@router.post("/register", response_model=None)
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    service = AuthService(db)
    try:
        user = await service.register(UserCreate(email=email, password=password))
    except EmailAlreadyRegisteredError:
        return templates.TemplateResponse(
            request, "register.html", {"error": "Этот email уже зарегистрирован"}, status_code=409
        )

    tokens = service.issue_tokens(user.id)
    response = RedirectResponse(url="/web/workspaces", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(ACCESS_TOKEN_COOKIE, tokens.access_token, httponly=True, samesite="lax")
    return response


@router.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/web/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response


# --- Workspaces ---


@router.get("/workspaces", response_class=HTMLResponse)
async def workspaces_page(
    request: Request,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    service = WorkspaceService(db)
    workspaces = await service.list_workspaces(current_user.id)
    return templates.TemplateResponse(
        request, "workspaces.html", {"user": current_user, "workspaces": workspaces}
    )


@router.post("/workspaces", response_class=HTMLResponse)
async def create_workspace_web(
    request: Request,
    name: str = Form(...),
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    service = WorkspaceService(db)
    await service.create_workspace(name, current_user.id)
    workspaces = await service.list_workspaces(current_user.id)
    return templates.TemplateResponse(
        request, "partials/workspace_list.html", {"workspaces": workspaces}
    )


@router.delete("/workspaces/{workspace_id}", response_class=HTMLResponse)
async def delete_workspace_web(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    service = WorkspaceService(db)
    try:
        await service.delete_workspace(workspace_id, current_user.id)
    except WorkspaceNotFoundError:
        pass  # уже удалён или чужой — для htmx достаточно тихо убрать элемент из DOM
    return HTMLResponse("")


@router.get("/workspaces/{workspace_id}", response_class=HTMLResponse, response_model=None)
async def workspace_detail_page(
    request: Request,
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> HTMLResponse | RedirectResponse:
    workspace_service = WorkspaceService(db)
    try:
        workspace = await workspace_service.get_owned_workspace(workspace_id, current_user.id)
    except WorkspaceNotFoundError:
        return RedirectResponse(url="/web/workspaces", status_code=status.HTTP_303_SEE_OTHER)

    document_service = DocumentService(db, storage)
    documents = await document_service.list_documents(workspace_id, current_user.id)

    return templates.TemplateResponse(
        request,
        "workspace_detail.html",
        {"user": current_user, "workspace": workspace, "documents": documents},
    )


@router.post(
    "/workspaces/{workspace_id}/documents",
    response_class=HTMLResponse,
    response_model=None,
)
async def upload_document_web(
    request: Request,
    workspace_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(get_current_web_user),
    db: AsyncSession = Depends(get_db),
    storage: FileStorage = Depends(get_storage),
) -> HTMLResponse | RedirectResponse:
    service = DocumentService(db, storage)
    content = await file.read()

    upload_error: str | None = None
    try:
        await service.upload_document(
            workspace_id=workspace_id,
            owner_id=current_user.id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except (UnsupportedFileTypeError, FileTooLargeError) as exc:
        upload_error = str(exc)
    except WorkspaceNotFoundError:
        return RedirectResponse(url="/web/workspaces", status_code=status.HTTP_303_SEE_OTHER)

    documents = await service.list_documents(workspace_id, current_user.id)
    return templates.TemplateResponse(
        request,
        "partials/document_list.html",
        {"documents": documents, "upload_error": upload_error},
    )
