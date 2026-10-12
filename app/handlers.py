import asyncio
import logging

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputMediaAudio,
    InputTextMessageContent,
)

from app import db
from app.config import ADMIN_CHAT_ID
from app.downloader import get_or_download
from app.states import BroadcastStates
from app.youtube import search_tracks

logger = logging.getLogger("handlers")
router = Router()


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "--:--"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await db.add_user(message.chat.id, message.from_user.username if message.from_user else None)

    bot_info = await message.bot.get_me()
    await message.answer(
        "Привет! Это музыкальный бот 🎧\n\n"
        f"Чтобы найти трек, набери в поле ввода в ЛЮБОМ чате:\n"
        f"<code>@{bot_info.username} название песни</code>\n\n"
        "Выпадет список результатов — жми на нужный, и трек придёт прямо в чат.",
        parse_mode="HTML",
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    if message.from_user is None or message.from_user.id != ADMIN_CHAT_ID:
        return  # тихо игнорируем — не палим команду посторонним

    await state.set_state(BroadcastStates.waiting_for_message)
    await message.answer(
        "Пришли сообщение (текст, фото, видео — что угодно), которое разослать всем пользователям.\n"
        "Для отмены — /cancel"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("Отменено.")


@router.message(BroadcastStates.waiting_for_message)
async def receive_broadcast_message(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_message_id=message.message_id, broadcast_chat_id=message.chat.id)
    await state.set_state(BroadcastStates.waiting_for_confirmation)

    user_ids = await db.get_all_user_ids()
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Разослать", callback_data="broadcast_confirm"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel"),
            ]
        ]
    )
    await message.answer(
        f"Сообщение выше будет разослано {len(user_ids)} пользователям, которые писали /start.\n"
        "Отправляем?",
        reply_markup=confirm_keyboard,
    )


@router.callback_query(F.data == "broadcast_cancel", BroadcastStates.waiting_for_confirmation)
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "broadcast_confirm", BroadcastStates.waiting_for_confirmation)
async def broadcast_confirm(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("⏳ Рассылаю…")

    source_chat_id = data["broadcast_chat_id"]
    source_message_id = data["broadcast_message_id"]
    user_ids = await db.get_all_user_ids()

    sent, failed = 0, 0
    for chat_id in user_ids:
        try:
            await bot.copy_message(chat_id=chat_id, from_chat_id=source_chat_id, message_id=source_message_id)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.copy_message(
                    chat_id=chat_id, from_chat_id=source_chat_id, message_id=source_message_id
                )
                sent += 1
            except Exception:
                failed += 1
        except TelegramForbiddenError:
            failed += 1  # пользователь заблокировал бота
        except Exception as e:
            logger.warning("Не удалось отправить %s: %s", chat_id, e)
            failed += 1
        await asyncio.sleep(0.05)  # не спамим Telegram API слишком быстро

    await callback.message.edit_text(f"Готово ✅\nДоставлено: {sent}\nНе доставлено: {failed}")


@router.inline_query()
async def handle_inline_query(inline_query: types.InlineQuery):
    query_text = inline_query.query.strip()
    if not query_text:
        return await inline_query.answer(
            results=[],
            switch_pm_text="Введите название трека…",
            switch_pm_parameter="help",
            cache_time=1,
        )

    try:
        tracks = await search_tracks(query_text)
    except Exception as e:
        logger.exception("Ошибка поиска: %s", e)
        return await inline_query.answer(results=[], cache_time=1)

    results = []
    for track in tracks:
        # сохраняем метаданные — они понадобятся в handle_chosen_inline_result,
        # когда придёт только youtube_id без остального контекста
        await db.upsert_track_metadata(track)

        loading_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="⏳ Загружаю трек…", callback_data="noop")]]
        )

        results.append(
            InlineQueryResultArticle(
                id=track["youtube_id"],
                title=track["title"],
                description=f"{track['artist']} · {format_duration(track['duration_seconds'])}",
                thumbnail_url=track["thumbnail_url"],
                input_message_content=InputTextMessageContent(
                    message_text=f"🎵 <b>{track['title']}</b>\n👤 {track['artist']}\n⏳ Загружаю…",
                    parse_mode="HTML",
                ),
                reply_markup=loading_keyboard,
            )
        )

    await inline_query.answer(results=results, cache_time=5, is_personal=True)


@router.callback_query(lambda c: c.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer("Трек ещё готовится, подождите пару секунд…")


@router.chosen_inline_result()
async def handle_chosen_inline_result(chosen: types.ChosenInlineResult, bot: Bot):
    youtube_id = chosen.result_id
    inline_message_id = chosen.inline_message_id
    if not inline_message_id:
        return  # без reply_markup Telegram не даёт inline_message_id — но у нас он всегда есть

    metadata = await db.get_track_metadata(youtube_id)
    title = metadata["title"] if metadata else "Трек"
    artist = metadata["artist"] if metadata else None

    try:
        telegram_file_id = await db.get_telegram_file_id(youtube_id)

        if not telegram_file_id:
            # Ещё ни разу не скачивали и не грузили на серверы Telegram —
            # делаем это сейчас через yt-dlp, затем шлём в приватный чат-склад,
            # чтобы получить file_id (напрямую загрузить файл в inline-сообщение нельзя —
            # так устроен Telegram Bot API).
            file_path = await get_or_download(youtube_id)
            storage_message = await bot.send_audio(
                chat_id=ADMIN_CHAT_ID,
                audio=FSInputFile(file_path),
                title=title,
                performer=artist,
            )
            telegram_file_id = storage_message.audio.file_id
            await db.set_telegram_file_id(youtube_id, telegram_file_id)

        await bot.edit_message_media(
            inline_message_id=inline_message_id,
            media=InputMediaAudio(media=telegram_file_id, title=title, performer=artist),
        )
    except Exception as e:
        logger.exception("Не удалось обработать трек %s: %s", youtube_id, e)
        try:
            await bot.edit_message_text(
                inline_message_id=inline_message_id,
                text=f"🎵 <b>{title}</b>\n👤 {artist}\n\n❌ Не удалось скачать трек. Попробуйте другой.",
                parse_mode="HTML",
            )
        except Exception:
            pass
