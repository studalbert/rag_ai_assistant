from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.workspaces import router as workspaces_router
from app.core.db import get_db
from app.web.routes import router as web_router

app = FastAPI(title="AI RAG Assistant")

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(web_router)


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/web/login")


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
