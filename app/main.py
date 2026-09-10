from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.workspaces import router as workspaces_router
from app.core.db import get_db

app = FastAPI(title="AI RAG Assistant")

app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(documents_router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
