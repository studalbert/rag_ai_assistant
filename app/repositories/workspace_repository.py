import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace


class WorkspaceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, name: str, owner_id: uuid.UUID) -> Workspace:
        workspace = Workspace(name=name, owner_id=owner_id)
        self.db.add(workspace)
        await self.db.commit()
        await self.db.refresh(workspace)
        return workspace

    async def list_by_owner(self, owner_id: uuid.UUID) -> list[Workspace]:
        result = await self.db.execute(
            select(Workspace).where(Workspace.owner_id == owner_id).order_by(Workspace.created_at)
        )
        return list(result.scalars().all())

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self.db.get(Workspace, workspace_id)

    async def delete(self, workspace: Workspace) -> None:
        await self.db.delete(workspace)
        await self.db.commit()