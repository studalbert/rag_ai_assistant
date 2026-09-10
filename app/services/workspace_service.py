import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace
from app.repositories.workspace_repository import WorkspaceRepository


class WorkspaceNotFoundError(Exception):
    """Бросаем и когда workspace не существует, и когда он принадлежит другому пользователю.

    Одинаковое сообщение/исключение для обоих случаев — намеренно: снаружи чужой workspace
    должен выглядеть так же, как несуществующий (иначе через enumeration можно узнавать
    чужие ID). Роутер превратит это в 404, а не в отдельные 403/404.
    """
    pass


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.repo = WorkspaceRepository(db)

    async def create_workspace(self, name: str, owner_id: uuid.UUID) -> Workspace:
        return await self.repo.create(name, owner_id)

    async def list_workspaces(self, owner_id: uuid.UUID) -> list[Workspace]:
        return await self.repo.list_by_owner(owner_id)

    async def get_owned_workspace(self, workspace_id: uuid.UUID, owner_id: uuid.UUID) -> Workspace:
        workspace = await self.repo.get_by_id(workspace_id)
        if workspace is None or workspace.owner_id != owner_id:
            raise WorkspaceNotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    async def delete_workspace(self, workspace_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        workspace = await self.get_owned_workspace(workspace_id, owner_id)
        await self.repo.delete(workspace)