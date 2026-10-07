import aiosqlite

from bot.config import settings

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS telegram_links (
    telegram_id INTEGER PRIMARY KEY,
    refresh_token TEXT NOT NULL,
    active_workspace_id TEXT,
    active_chat_id TEXT
)
"""


async def init_db() -> None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(_CREATE_TABLE_SQL)
        await db.commit()


async def save_link(telegram_id: int, refresh_token: str) -> None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(
            "INSERT INTO telegram_links (telegram_id, refresh_token) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET refresh_token = excluded.refresh_token",
            (telegram_id, refresh_token),
        )
        await db.commit()


async def get_refresh_token(telegram_id: int) -> str | None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        async with db.execute(
            "SELECT refresh_token FROM telegram_links WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def update_refresh_token(telegram_id: int, refresh_token: str) -> None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(
            "UPDATE telegram_links SET refresh_token = ? WHERE telegram_id = ?",
            (refresh_token, telegram_id),
        )
        await db.commit()


async def set_active_workspace(telegram_id: int, workspace_id: str) -> None:
    # Смена workspace сбрасывает активный chat_id — новый диалог начинается
    # в новом workspace, не продолжая случайно историю из предыдущего
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(
            "UPDATE telegram_links SET active_workspace_id = ?, active_chat_id = NULL "
            "WHERE telegram_id = ?",
            (workspace_id, telegram_id),
        )
        await db.commit()


async def get_active_workspace(telegram_id: int) -> str | None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        async with db.execute(
            "SELECT active_workspace_id FROM telegram_links WHERE telegram_id = ?",
            (telegram_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


async def set_active_chat(telegram_id: int, chat_id: str) -> None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(
            "UPDATE telegram_links SET active_chat_id = ? WHERE telegram_id = ?",
            (chat_id, telegram_id),
        )
        await db.commit()


async def get_active_chat(telegram_id: int) -> str | None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        async with db.execute(
            "SELECT active_chat_id FROM telegram_links WHERE telegram_id = ?", (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


async def clear_active_chat(telegram_id: int) -> None:
    async with aiosqlite.connect(settings.bot_db_path) as db:
        await db.execute(
            "UPDATE telegram_links SET active_chat_id = NULL WHERE telegram_id = ?",
            (telegram_id,),
        )
        await db.commit()

