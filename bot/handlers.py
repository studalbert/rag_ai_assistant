import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import api_client, storage
from bot.api_client import AskError, LinkError, NotLinkedError

router = Router()

EDIT_INTERVAL_SECONDS = 1.2  # не чаще — иначе Telegram начнёт отклонять правки (flood control)


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
        "Аккаунт успешно привязан! Теперь выберите базу знаний командой /workspaces."
    )


@router.message(Command("workspaces"))
async def handle_workspaces(message: Message) -> None:
    telegram_id = message.from_user.id

    try:
        workspaces = await api_client.list_workspaces(telegram_id)
    except NotLinkedError as exc:
        await message.answer(str(exc))
        return

    if not workspaces:
        await message.answer("У вас пока нет баз знаний — создайте их на сайте.")
        return

    buttons = [
        [InlineKeyboardButton(text=workspace["name"], callback_data=f"ws:{workspace['id']}")]
        for workspace in workspaces
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Выберите базу знаний:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("ws:"))
async def handle_workspace_selection(callback: CallbackQuery) -> None:
    workspace_id = callback.data.removeprefix("ws:")
    telegram_id = callback.from_user.id

    await storage.set_active_workspace(telegram_id, workspace_id)

    workspace_name = "выбранная база знаний"
    for row in callback.message.reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback.data:
                workspace_name = button.text

    await callback.answer()
    await callback.message.edit_text(
        f"✅ Активная база знаний: {workspace_name}\n\nТеперь просто напишите вопрос."
    )


@router.message(Command("newchat"))
async def handle_newchat(message: Message) -> None:
    await storage.clear_active_chat(message.from_user.id)
    await message.answer("Начат новый диалог (в той же базе знаний).")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_question(message: Message) -> None:
    telegram_id = message.from_user.id

    workspace_id = await storage.get_active_workspace(telegram_id)
    if workspace_id is None:
        await message.answer("Сначала выберите базу знаний: /workspaces")
        return

    chat_id = await storage.get_active_chat(telegram_id)
    thinking_message = await message.answer("⏳ Думаю...")

    answer_parts: list[str] = []
    sources: list[dict] = []
    last_edit_at = 0.0

    try:
        async for event in api_client.ask_stream(telegram_id, workspace_id, message.text, chat_id):
            event_type = event["type"]

            if event_type == "chat_id":
                await storage.set_active_chat(telegram_id, event["chat_id"])
            elif event_type == "sources":
                sources = event["sources"]
            elif event_type == "token":
                answer_parts.append(event["content"])
                now = time.monotonic()
                if now - last_edit_at >= EDIT_INTERVAL_SECONDS:
                    last_edit_at = now
                    await _try_edit(thinking_message, "".join(answer_parts) + " ▌")
            elif event_type == "error":
                await _try_edit(thinking_message, f"⚠️ Ошибка: {event['message']}")
                return
    except NotLinkedError as exc:
        await _try_edit(thinking_message, str(exc))
        return
    except AskError as exc:
        await _try_edit(thinking_message, f"Не удалось получить ответ: {exc}")
        return

    final_text = "".join(answer_parts) or "(пустой ответ)"
    if sources:
        source_lines = "\n".join(
            f"[{index}] {source['filename']}" for index, source in enumerate(sources, start=1)
        )
        final_text += f"\n\nИсточники:\n{source_lines}"

    await _try_edit(thinking_message, final_text)


async def _try_edit(message: Message, text: str) -> None:
    """Редактирование сообщения с защитой от двух частых, безопасных для
    игнорирования ошибок Telegram: "текст не изменился" и превышение лимита
    частоты запросов (в последнем случае просто пропускаем этот конкретный
    промежуточный апдейт — следующий токен попробует снова)."""
    try:
        await message.edit_text(text)
    except TelegramRetryAfter:
        pass
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
