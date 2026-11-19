import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions

TOKEN = "BOT_TOKEN"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Створюємо кнопки під повідомленням
def get_offer_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Отклонить", callback_data="offer_decline"),
                InlineKeyboardButton(text="Принять", callback_data="offer_accept")
            ]
        ]
    )
    return keyboard

# Команда для відправки картки-пропозиції
@dp.message(Command("offer"))
async def send_offer(message: types.Message):
    # Посилання на реальний NFT-подарунок у Telegram, щоб підтягнулося прев'ю зверху
    nft_link = "https://t.me/nft/FaithAmulet-84923"
    
    # Формуємо текст з HTML-розміткою
    text = (
        f'Пользователь <a href="tg://user?id={message.from_user.id}">Е</a>\n'
        f'предлагает вам 11000 ⭐️ за подарок\n'
        f'<a href="{nft_link}">FaithAmulet #84923</a>\n\n'
        f'Предложение действует еще 23ч 58м.'
    )

    # Налаштування прев'ю посилання (щоб картинка була великою і зверху, як на скріншоті)
    preview_options = LinkPreviewOptions(
        url=nft_link,
        prefer_large_media=True,
        show_above_text=True
    )

    await message.answer(
        text=text,
        parse_mode="HTML",
        link_preview_options=preview_options,
        reply_markup=get_offer_keyboard()
    )

# Обробка натискання на кнопку "Отклонить"
@dp.callback_query(F.data == "offer_decline")
async def process_decline(callback: types.CallbackQuery):
    await callback.answer("Предложение отклонено", show_alert=True)
    # Можна видалити кнопки або змінити текст після натискання:
    # await callback.message.edit_reply_markup(reply_markup=None)

# Обробка натискання на кнопку "Принять"
@dp.callback_query(F.data == "offer_accept")
async def process_accept(callback: types.CallbackQuery):
    await callback.answer("Предложение принято!", show_alert=True)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
