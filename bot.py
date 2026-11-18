import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

# Ваш токен бота
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# Створюємо диспетчер
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """
    Цей обробник спрацьовує на команду /start
    """
    await message.answer(f"Привіт, {html.bold(message.from_user.full_name)}! Я ваш новий бот.")

@dp.message()
async def echo_handler(message: Message) -> None:
    """
    Ехо-обробник: відправляє назад те саме повідомлення, що написав користувач.
    """
    try:
        # Просто надсилаємо текст назад
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        await message.answer("Я розумію лише текстові повідомлення!")

async def main() -> None:
    # Ініціалізація бота з налаштуваннями за замовчуванням
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # Запуск процесу опита (polling)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
