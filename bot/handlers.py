from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot import api_client
from bot.api_client import LinkError

router = Router()


@router.message(Command("start"))
async def handle_start(message: Message) -> None:
    await message.answer(
        "Привет! Я помогу задавать вопросы по твоим документам.\n\n"
        "Сначала привяжи аккаунт: зайди на сайт, залогинься, получи код на странице "
        "со списком баз знаний, и отправь мне команду /link <код>."
    )


@router.message(Command("link"))
async def handle_link(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Использование: /link <код>")
        return

    code = command.args.strip()
    telegram_id = message.from_user.id

    try:
        await api_client.link_account(code, telegram_id)
    except LinkError as exc:
        await message.answer(f"Не удалось привязать аккаунт: {exc}")
        return

    await message.answer(
        "Аккаунт успешно привязан! Дальше — выбор базы знаний и вопросы "
        "(появятся на следующих шагах)."
    )