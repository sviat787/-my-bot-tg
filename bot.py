import asyncio
import html
import os
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from aiohttp import web

# Токен береться зі змінної середовища BOT_TOKEN (додаєш у Render)
TOKEN = os.getenv("BOT_TOKEN")

# Адміни за username (у нижньому регістрі, без @)
DEFAULT_ADMIN_USERNAMES = {"sviat787", "boorn777"}

# Додаткові адміни за числовими ID через кому в Render: ADMIN_IDS=123456789,987654321
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

# Зберігання статистики та користувачів у пам'яті (для Render без БД)
known_users: set[int] = set()
stats = {
    "offers_created": 0,
    "accepted": 0,
    "declined": 0,
}


class OfferForm(StatesGroup):
    waiting_for_amount = State()
    waiting_for_currency = State()


class AdminBroadcast(StatesGroup):
    waiting_for_message = State()


def is_admin(user: types.User | None) -> bool:
    if not user:
        return False
    if user.id in EXTRA_ADMIN_IDS:
        return True
    if user.username and user.username.lower() in DEFAULT_ADMIN_USERNAMES:
        return True
    return False


def track_user(user: types.User | None):
    if user:
        known_users.add(user.id)


def format_nft_title(nft_url: str) -> str:
    """Перетворює https://t.me/nft/FaithAmulet-84923 на FaithAmulet #84923."""
    slug = nft_url.rstrip("/").split("/")[-1]
    if "-" in slug:
        name, num = slug.rsplit("-", 1)
        return f"{name} #{num}"
    return slug


def normalize_currency(raw: str | None) -> str | None:
    """Повертає 'stars' або 'gram', якщо валюта підтримується."""
    if not raw:
        return None
    val = raw.strip().lower()
    if val in {"stars", "star", "⭐️", "⭐", "🌟"}:
        return "stars"
    if val in {"gram", "grams", "грам", "грами", "грамів"}:
        return "gram"
    return None


def format_currency_label(currency: str) -> str:
    return "⭐️" if currency == "stars" else "GRAM"


def get_offer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Отклонить", callback_data="offer_decline"),
                InlineKeyboardButton(text="Принять", callback_data="offer_accept"),
            ]
        ]
    )


def get_currency_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐️ Stars", callback_data="cur_stars"),
                InlineKeyboardButton(text="GRAM", callback_data="cur_gram"),
            ]
        ]
    )


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
                InlineKeyboardButton(text="📢 Розсилка", callback_data="admin_broadcast"),
            ],
            [
                InlineKeyboardButton(text="🎁 Створити картку", callback_data="admin_new_offer"),
                InlineKeyboardButton(text="👑 Адміни", callback_data="admin_list"),
            ],
        ]
    )


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

    await target_message.answer(
        text=text,
        parse_mode="HTML",
        link_preview_options=preview_options,
        reply_markup=get_offer_keyboard(),
    )


# ---------- Команди користувача ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()

    text = (
        "Привіт! Кидай одразу в одному повідомленні:\n"
        "<code>посилання_на_nft сума валюта</code>\n\n"
        "Приклади:\n"
        "• <code>https://t.me/nft/FaithAmulet-84923 11000 stars</code>\n"
        "• <code>https://t.me/nft/FaithAmulet-84923 250 gram</code>\n\n"
        "Або просто скинь посилання на NFT — я запитаю суму й валюту."
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


# ---------- Адмін-панель ----------
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    track_user(message.from_user)
    await state.clear()
    if not is_admin(message.from_user):
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return

    await message.answer(
        "🛠 <b>Адмін-панель</b>\nОбери потрібну дію:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )


@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user):
        await callback.answer("Немає доступу", show_alert=True)
        return

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"• Користувачів у сесії: <b>{len(known_users)}</b>\n"
        f"• Створено карток: <b>{stats['offers_created']}</b>\n"
        f"• Натиснуто «Принять»: <b>{stats['accepted']}</b>\n"
        f"• Натиснуто «Отклонить»: <b>{stats['declined']}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "admin_list")
async def cb_admin_list(callback: types.CallbackQuery):
