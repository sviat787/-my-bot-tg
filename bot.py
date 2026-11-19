import asyncio
import html
import os
import re
import uuid
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")

DEFAULT_ADMIN_USERNAMES = {"sviat787", "boorn777"}

EXTRA_ADMIN_IDS: set[int] = set()
for raw_id in os.getenv("ADMIN_IDS", "").split(","):
    raw_id = raw_id.strip()
    if raw_id.isdigit():
        EXTRA_ADMIN_IDS.add(int(raw_id))

if not TOKEN:
    raise RuntimeError("Не задано змінну середовища BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

NFT_URL_REGEX = re.compile(r"(https?://t\.me/nft/[A-Za-z0-9_]+-\d+)", re.IGNORECASE)
AMOUNT_REGEX = re.compile(r"^\d+(?:[.,]\d+)?$")

known_users: set[int] = set()
active_offers: dict = {} # Тут зберігаються створені картки
stats = {
    "offers_created": 0,
    "accepted": 0,
    "declined": 0,
}

class OfferForm(StatesGroup):
    waiting_for_data = State()

class AdminBroadcast(StatesGroup):
    waiting_for_message = State()

def is_admin(user: types.User | None) -> bool:
    if not user: return False
    if user.id in EXTRA_ADMIN_IDS: return True
    if user.username and user.username.lower() in DEFAULT_ADMIN_USERNAMES: return True
    return False

def track_user(user: types.User | None):
    if user: known_users.add(user.id)

def format_nft_title(nft_url: str) -> str:
    slug = nft_url.rstrip("/").split("/")[-1]
    if "-" in slug:
        name, num = slug.rsplit("-", 1)
        return f"{name} #{num}"
    return slug

def normalize_currency(raw: str | None) -> str | None:
    if not raw: return None
    val = raw.strip().lower()
    if val in {"stars", "star", "⭐️", "⭐", "🌟"}: return "stars"
    if val in {"gram", "grams", "грам", "грами", "грамів"}: return "gram"
    return None

def format_currency_label(currency: str) -> str:
    return "⭐️" if currency == "stars" else "GRAM"

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="📢 Розсилка", callback_data="admin_broadcast"),
        ],
        [
            InlineKeyboardButton(text="🎁 Створити картку", callback_data="admin_new_offer"),
            InlineKeyboardButton(text="👑 Адміни", callback_data="admin_list"),
        ],
    ])
    @dp.callback_query(F.data.startswith("offer_decline:"))
    async def cb_offer_decline(callback: types.CallbackQuery):
        offer_id = callback.data.split(":")[1]
        offer = active_offers.get(offer_id)
    
    stats["declined"] += 1
    await callback.answer("Предложение отклонено", show_alert=True)
    
    if offer:
        # Повідомляємо творця картки (тебе), що покупець відмовився
        try:
            await bot.send_message(
                offer["creator_id"],
                f"❌ Користувач <a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a> відхилив вашу пропозицію щодо {offer['amount']} {format_currency_label(offer['currency'])}.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.callback_query(F.data.startswith("offer_accept:"))
async def cb_offer_accept(callback: types.CallbackQuery):
    offer_id = callback.data.split(":")[1]
    offer = active_offers.get(offer_id)
    
    stats["accepted"] += 1
    await callback.answer("Ви прийняли пропозицію! Продавець отримав сповіщення.", show_alert=True)
    
    if offer:
        # Повідомляємо творця картки (тебе), що угоду прийнято
        try:
            admin_msg = (
                f"✅ <b>Вашу пропозицію прийнято!</b>\n\n"
                f"Покупець: <a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a> (@{callback.from_user.username or 'немає'})\n"
                f"Сума: {offer['amount']} {format_currency_label(offer['currency'])}\n"
                f"NFT: <a href='{offer['nft_url']}'>{format_nft_title(offer['nft_url'])}</a>\n\n"
                f"Напишіть йому, щоб завершити обмін!"
            )
            await bot.send_message(offer["creator_id"], admin_msg, parse_mode="HTML")
        except Exception as e:
            print(f"Помилка відправки: {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()
    if not is_admin(message.from_user):
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return
    await message.answer("🛠 <b>Адмін-панель</b>\nОбери дію:", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user):
        await callback.answer("Немає доступу", show_alert=True)
        return
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"• Користувачів: <b>{len(known_users)}</b>\n"
        f"• Карток створено: <b>{stats['offers_created']}</b>\n"
        f"• Прийнято: <b>{stats['accepted']}</b>\n"
        f"• Відхилено: <b>{stats['declined']}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_list")
async def cb_admin_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user):
        await callback.answer("Немає доступу", show_alert=True)
        return
    usernames = ", ".join(f"@{u}" for u in sorted(DEFAULT_ADMIN_USERNAMES)) or "немає"
    extra_ids = ", ".join(str(i) for i in sorted(EXTRA_ADMIN_IDS)) or "немає"
    text = (
        "👑 <b>Список адміністраторів</b>\n\n"
        f"• Username: <code>{html.escape(usernames)}</code>\n"
        f"• ID: <code>{html.escape(extra_ids)}</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
    await callback.answer()

async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
async def send_offer_card(
    target_message: types.Message,
    sender: types.User,
    nft_url: str,
    amount: str,
    currency: str,
):
    nft_title = html.escape(format_nft_title(nft_url))
    safe_url = html.escape(nft_url, quote=True)
    user_label = html.escape(sender.first_name or "Пользователь")
    cur_label = format_currency_label(currency)

    # Генеруємо унікальний ID для картки
    offer_id = str(uuid.uuid4())[:8]
    
    # Запам'ятовуємо, хто створив цю картку
    active_offers[offer_id] = {
        "creator_id": sender.id,
        "creator_name": sender.first_name,
        "nft_url": nft_url,
        "amount": amount,
        "currency": currency
    }

    text = (
        f'Пользователь <a href="tg://user?id={sender.id}">{user_label}</a>\n'
        f"предлагает вам {html.escape(amount)} {cur_label} за подарок\n"
        f'<a href="{safe_url}">{nft_title}</a>\n\n'
        f"Предложение действует еще 23ч 58м."
    )

    preview_options = LinkPreviewOptions(
        url=nft_url,
        prefer_large_media=True,
        show_above_text=True,
    )

    stats["offers_created"] += 1

    # Прив'язуємо ID до кнопок
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Отклонить", callback_data=f"offer_decline:{offer_id}"),
        InlineKeyboardButton(text="Принять", callback_data=f"offer_accept:{offer_id}"),
    ]])

    await target_message.answer(
        text=text,
        parse_mode="HTML",
        link_preview_options=preview_options,
        reply_markup=keyboard,
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()
    text = (
        "Привіт! Щоб створити оффер, просто надішли мені повідомлення у форматі:\n"
        "<code>посилання_на_nft сума валюта</code>\n\n"
        "Приклади:\n"
        "• <code>https://t.me/nft/FaithAmulet-84923 11000 stars</code>\n"
        "• <code>https://t.me/nft/FaithAmulet-84923 250 gram</code>"
    )
    if is_admin(message.from_user):
        text += "\n\n👑 Ви маєте права адміністратора. Використовуйте /admin"
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("offer"))
async def cmd_offer(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()
    await message.answer(
        "Скинь посилання на NFT, суму та валюту (<b>stars</b> або <b>gram</b>).\n"
        "Наприклад: <code>https://t.me/nft/FaithAmulet-84923 11000 stars</code>",
        parse_mode="HTML",
    )

@dp.message(F.text)
async def process_offer_message(message: types.Message, state: FSMContext):
    if message.text.startswith("/"):
        return

    track_user(message.from_user)

    nft_match = NFT_URL_REGEX.search(message.text)
    if not nft_match:
        return

    nft_url = nft_match.group(1)
    rest_text = message.text.replace(nft_url, "").strip()
    parts = rest_text.split()

    if len(parts) >= 2:
        amount = parts[0]
        currency = normalize_currency(parts[1])

        if AMOUNT_REGEX.match(amount) and currency:
            await send_offer_card(
                target_message=message,
                sender=message.from_user,
                nft_url=nft_url,
                amount=amount,
                currency=currency
            )
            return

    await message.answer(
        "⚠️ Я знайшов посилання, але не зрозумів суму чи валюту.\n"
        "Напиши в форматі: <code>посилання сума валюта</code>\n"
        "Наприклад: <code>https://t.me/nft/FaithAmulet-84923 500 stars</code>",
        parse_mode="HTML"
    )
    @dp.callback_query(F.data.startswith("offer_decline:"))
    async def cb_offer_decline(callback: types.CallbackQuery):
    offer_id = callback.data.split(":")[1]
    offer = active_offers.get(offer_id)
    
    stats["declined"] += 1
    await callback.answer("Предложение отклонено", show_alert=True)
    
    if offer:
        # Повідомляємо творця картки (тебе), що покупець відмовився
        try:
            await bot.send_message(
                offer["creator_id"],
                f"❌ Користувач <a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a> відхилив вашу пропозицію щодо {offer['amount']} {format_currency_label(offer['currency'])}.",
                parse_mode="HTML"
            )
        except Exception:
            pass

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.callback_query(F.data.startswith("offer_accept:"))
async def cb_offer_accept(callback: types.CallbackQuery):
    offer_id = callback.data.split(":")[1]
    offer = active_offers.get(offer_id)
    
    stats["accepted"] += 1
    await callback.answer("Ви прийняли пропозицію! Продавець отримав сповіщення.", show_alert=True)
    
    if offer:
        # Повідомляємо творця картки (тебе), що угоду прийнято
        try:
            admin_msg = (
                f"✅ <b>Вашу пропозицію прийнято!</b>\n\n"
                f"Покупець: <a href='tg://user?id={callback.from_user.id}'>{callback.from_user.first_name}</a> (@{callback.from_user.username or 'немає'})\n"
                f"Сума: {offer['amount']} {format_currency_label(offer['currency'])}\n"
                f"NFT: <a href='{offer['nft_url']}'>{format_nft_title(offer['nft_url'])}</a>\n\n"
                f"Напишіть йому, щоб завершити обмін!"
            )
            await bot.send_message(offer["creator_id"], admin_msg, parse_mode="HTML")
        except Exception as e:
            print(f"Помилка відправки: {e}")

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()
    if not is_admin(message.from_user):
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return
    await message.answer("🛠 <b>Адмін-панель</b>\nОбери дію:", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user):
        await callback.answer("Немає доступу", show_alert=True)
        return
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"• Користувачів: <b>{len(known_users)}</b>\n"
        f"• Карток створено: <b>{stats['offers_created']}</b>\n"
        f"• Прийнято: <b>{stats['accepted']}</b>\n"
        f"• Відхилено: <b>{stats['declined']}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "admin_list")
async def cb_admin_list(callback: types.CallbackQuery):
    if not is_admin(callback.from_user):
        await callback.answer("Немає доступу", show_alert=True)
        return
    usernames = ", ".join(f"@{u}" for u in sorted(DEFAULT_ADMIN_USERNAMES)) or "немає"
    extra_ids = ", ".join(str(i) for i in sorted(EXTRA_ADMIN_IDS)) or "немає"
    text = (
        "👑 <b>Список адміністраторів</b>\n\n"
        f"• Username: <code>{html.escape(usernames)}</code>\n"
        f"• ID: <code>{html.escape(extra_ids)}</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
    await callback.answer()

async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
