import logging

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from asgiref.sync import sync_to_async
from django.conf import settings

from .services import LoginAttemptError, confirm_login_attempt

logger = logging.getLogger(__name__)

dp = Dispatcher()


@dp.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    token = command.args
    if not token:
        await message.answer(
            "Salom! Saytda “Telegram orqali kirish” tugmasini bosing — "
            "shu botga tasdiqlash uchun qaytadan yo'naltirilasiz."
        )
        return

    # Telegram ID — Telegram update'ning o'zidan olinadi, foydalanuvchi
    # yuborgan matndan emas: soxtalashtirib bo'lmaydi.
    telegram_user_id = message.from_user.id

    try:
        await sync_to_async(confirm_login_attempt)(token, telegram_user_id)
    except LoginAttemptError as exc:
        await message.answer(f"❌ Kirish tasdiqlanmadi: {exc}")
        return

    await message.answer(
        "✅ Kirish tasdiqlandi! Endi saytga qaytib, davom etishingiz mumkin."
    )


async def run_bot() -> None:
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN .env faylida ko'rsatilmagan")

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
