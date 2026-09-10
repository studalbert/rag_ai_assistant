import uuid
from pathlib import Path
from typing import Protocol


class FileStorage(Protocol):
    """Интерфейс хранилища. Локальная ФС сейчас, S3/MinIO — потом,
    без изменения кода, который этим интерфейсом пользуется."""

    async def save(self, content: bytes, original_filename: str) -> str:
        """Сохраняет файл, возвращает путь/ключ, по которому его потом найти."""
        ...

    async def read(self, file_path: str) -> bytes:
        """Читает файл обратно по пути/ключу, который вернул save()."""
        ...


class LocalFileStorage:
    """Хранит файлы на локальном диске. Годится для dev и портфолио-проекта;
    в реальном продакшене с несколькими инстансами приложения так делать нельзя —
    каждый инстанс видел бы только свою файловую систему."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, content: bytes, original_filename: str) -> str:
        # Генерируем случайное имя, чтобы не было коллизий и нельзя было
        # угадать/перебрать пути чужих файлов
        extension = Path(original_filename).suffix
        stored_name = f"{uuid.uuid4()}{extension}"
        file_path = self.base_dir / stored_name

        file_path.write_bytes(content)
        return str(file_path)

    async def read(self, file_path: str) -> bytes:
        return Path(file_path).read_bytes()