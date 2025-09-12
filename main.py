# main.py
import asyncio
import logging
import os
import json
from contextlib import asynccontextmanager
from datetime import datetime, date as _date, time as _time, UTC, timedelta

import asyncpg
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat,
    ChatMemberUpdated, Update
)
from aiogram.utils.markdown import hbold


# ============================= WEBHOOK + FastAPI =============================
import os
from fastapi import FastAPI, Request
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

app = FastAPI()  # <-- это ВАЖНО

# читаем ENV из начала файла (они уже загружены load_dotenv())
WEBHOOK_BASE_URL   = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
if not WEBHOOK_BASE_URL:
    raise RuntimeError("WEBHOOK_BASE_URL is not set")
WEBHOOK_SECRET_PATH = os.getenv("WEBHOOK_SECRET_PATH", "hook")
WEBHOOK_PATH        = f"/webhook/{WEBHOOK_SECRET_PATH}"
WEBHOOK_URL         = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"
PORT                = int(os.getenv("PORT", "10000"))

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    assert bot is not None and dp is not None, "Bot/Dispatcher not ready yet"
    data = await request.json()
    logger.info("Webhook update: %s", json.dumps(data, ensure_ascii=False))
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/", include_in_schema=False)
async def health():
    return {"status": "ok"}


# ---------- ВАЖНО: ГЛОБАЛЬНЫЙ ASGI app ----------

# Глобальные объекты (инициализируем в on_startup)
bot: Bot | None = None
dp: Dispatcher | None = None

@app.get("/")
@app.get("/health")
@app.get("/healthz")
async def health():
    return "ok"

@app.on_event("startup")
async def on_startup():
    global bot, dp

    # БД
    await init_db_pool()

    # Бот и диспетчер
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    dp.include_router(guard)

    # Команды
    for uid in STAFF_USER_IDS:
        try:
            await set_chat_admin_commands(bot, uid, "ru")
        except Exception:
            pass
    if ADMIN_CHAT_ID:
        await set_chat_admin_commands(bot, ADMIN_CHAT_ID, "ru")
    await set_default_commands(bot)

    # Регистрируем вебхук на свой Render-URL
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

@app.on_event("shutdown")
async def on_shutdown():
    if bot:
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass

# Приём апдейтов от Telegram (должен совпасть с WEBHOOK_PATH)
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    assert bot is not None and dp is not None, "Bot/Dispatcher not ready yet"
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

# ============================= I18N =============================
LANGS = ("ru", "lv", "en")

I18N = {
    "ru": {
        "start": "👋 Привет! Я бот для бронирования столиков.\n\nНажмите «{btn_book}» и ответьте на вопросы — это быстро.",
        "choose_lang": "🌍 Выберите язык:",
        "btn_book": "Забронировать столик",
        "btn_menu": "Посмотреть меню",
        "btn_cancel": "Отмена",
        "btn_change_lang": "🌍 Сменить язык",
        "ask_date": "🗓 Введите дату (ДД.ММ.ГГГГ), напр.: 05.09.2025",
        "ask_time": "⏰ Введите время (ЧЧ:ММ), напр.: 19:30",
        "ask_guests": "👥 Сколько гостей? (числом)",
        "ask_table": "🪑 Выберите столик:",
        "no_tables": "😕 На это время свободных столиков нет. Попробуйте другое время.",
        "ask_name": "🧾 Ваше имя для брони?",
        "ask_phone": "📞 Ваш телефон (для подтверждения)?",
        "cancelled": "Отменено.",
        "thanks": "✅ Спасибо! Мы получили вашу заявку и скоро свяжемся.",
        "menu": "📋 Меню: {url}",
        "menu_empty": "📋 Меню пока не добавлено. Укажите MENU_URL в .env",
        "id": "Ваш chat_id: {id}",
        "err_date_format": "Введите дату в формате ДД.ММ.ГГГГ (например 05.09.2025)",
        "err_date_past": "Дата в прошлом",
        "err_time_format": "Введите время в формате 19:30 (допустимо 19.30 или 1930).",
        "err_time_hours": "Брони принимаются с {open} до {close}.",
        "err_guests_nan": "Введите число гостей, напр. 2",
        "err_guests_range": "Количество гостей от 1 до 30",
        "err_name_short": "Имя слишком короткое. Попробуйте ещё раз.",
        "err_phone_short": "Телефон выглядит слишком коротким. Введите ещё раз.",
        "lang_set": "✅ Язык сохранён.",
        "btn_lang_ru": "🇷🇺 Русский",
        "btn_lang_lv": "🇱🇻 Latviešu",
        "btn_lang_en": "🇬🇧 English",
        "user_confirmed": "✅ Ваша бронь подтверждена! До встречи!",
        "user_cancelled": "❌ К сожалению, бронь отменена. Свяжитесь с нами для переноса.",
        "admin_new": "📩 Новая бронь:",
        "admin_note_confirmed": "✅ Подтверждено администратором.",
        "admin_note_cancelled": "❌ Отменено администратором.",
        "btn_admin_confirm": "✅ Подтвердить",
        "btn_admin_cancel": "❌ Отменить",
        "admin_field_date": "Дата",
        "admin_field_time": "Время",
        "admin_field_table": "Столик",
        "admin_field_guests": "Гостей",
        "admin_field_name": "Имя",
        "admin_field_phone": "Телефон",
        "admin_field_user": "От пользователя",
        "btn_admin_panel": "👑 Админ-панель",
        "btn_admin_delete": "🗑 Удалить…",
        "admin_status_label": "Статус",
        "admin_filter_all": "все",
        "admin_filter_new": "новые",
        "admin_filter_confirmed": "подтверждённые",
        "admin_filter_cancelled": "отменённые",
        "admin_list_header": "📋 Брони (page {page}, {status_label}: {status}):",
        "empty": "Пусто.",
        "enter_booking_id": "Введите номер брони (ID), например: 12",
        "ask_id": "Укажи ID: /del 12  (или просто напиши число)",
        "id_must_be_number": "ID должен быть числом. Пример: /del 12",
        "need_number": "Нужно число. Пример: 12",
        "booking_deleted": "Бронь #{id} удалена.",
        "booking_not_found": "Бронь #{id} не найдена.",
        "ok": "ОК",
        "done_confirmed": "Подтверждено",
        "done_cancelled": "Отменено",
        "done_deleted": "Удалено",
        "reply_stub": "Меню"
    },
    "lv": {
        "start": "👋 Sveiki! Es esmu galdu rezervēšanas bots.\n\nNospiediet «{btn_book}» un atbildiet uz jautājumiem — tas ir ātri.",
        "choose_lang": "🌍 Izvēlieties valodu:",
        "btn_book": "Rezervēt galdu",
        "btn_menu": "Apskatīt ēdienkarti",
        "btn_cancel": "Atcelt",
        "btn_change_lang": "🌍 Valoda",
        "ask_date": "🗓 Ievadiet datumu (DD.MM.GGGG), piem.: 05.09.2025",
        "ask_time": "⏰ Ievadiet laiku (HH:MM), piem.: 19:30",
        "ask_guests": "👥 Cik viesu? (skaitlis)",
        "ask_table": "🪑 Izvēlieties galdu:",
        "no_tables": "😕 Šim laikam brīvu galdu nav. Pamēģiniet citu laiku.",
        "ask_name": "🧾 Jūsu vārds rezervācijai?",
        "ask_phone": "📞 Jūsu tālrunis (apstiprināšanai)?",
        "cancelled": "Atcelts.",
        "thanks": "✅ Paldies! Mēs saņēmām jūsu pieteikumu un drīz sazināsimies.",
        "menu": "📋 Ēdienkarte: {url}",
        "menu_empty": "📋 Ēdienkarte vēl nav pievienota. Norādiet MENU_URL .env failā",
        "id": "Jūsu chat_id: {id}",
        "err_date_format": "Ievadiet datumu formātā DD.MM.GGGG (piem. 05.09.2025)",
        "err_date_past": "Datums ir pagātnē",
        "err_time_format": "Ievadiet laiku formātā 19:30 (atļauts 19.30 vai 1930).",
        "err_time_hours": "Rezervācijas pieņem {open}–{close}.",
        "err_guests_nan": "Ievadiet viesu skaitu, piem. 2",
        "err_guests_range": "Viesu skaits no 1 līdz 30",
        "err_name_short": "Vārds ir pārāk īss. Mēģiniet vēlreiz.",
        "err_phone_short": "Tālruņa numurs izskatās pārāk īss. Ievadiet vēlreiz.",
        "lang_set": "✅ Valoda saglabāta.",
        "btn_lang_ru": "🇷🇺 Krievu",
        "btn_lang_lv": "🇱🇻 Latviešu",
        "btn_lang_en": "🇬🇧 Angļu",
        "user_confirmed": "✅ Jūsu rezervācija ir apstiprināta! Uz tikšanos!",
        "user_cancelled": "❌ Diemžēl rezervācija ir atcelta. Sazinieties ar mums, lai pārceltu.",
        "admin_new": "📩 Jauna rezervācija:",
        "admin_note_confirmed": "✅ Apstiprināts administratora.",
        "admin_note_cancelled": "❌ Atcelts administratora.",
        "btn_admin_confirm": "✅ Apstiprināt",
        "btn_admin_cancel": "❌ Atcelt",
        "admin_field_date": "Datums",
        "admin_field_time": "Laiks",
        "admin_field_table": "Galds",
        "admin_field_guests": "Viesi",
        "admin_field_name": "Vārds",
        "admin_field_phone": "Tālrunis",
        "admin_field_user": "No lietotāja",
        "btn_admin_panel": "👑 Admin panelis",
        "btn_admin_delete": "🗑 Dzēst…",
        "admin_status_label": "Statuss",
        "admin_filter_all": "visi",
        "admin_filter_new": "jauni",
        "admin_filter_confirmed": "apstiprināti",
        "admin_filter_cancelled": "atcelti",
        "admin_list_header": "📋 Rezervācijas (page {page}, {status_label}: {status}):",
        "empty": "Tukšs.",
        "enter_booking_id": "Ievadiet rezervācijas ID, piem.: 12",
        "ask_id": "Norādi ID: /del 12 (vai vienkārši skaitli)",
        "id_must_be_number": "ID jābūt skaitlim. Piemērs: /del 12",
        "need_number": "Nepieciešams skaitlis. Piemērs: 12",
        "booking_deleted": "Rezervācija #{id} dzēsta.",
        "booking_not_found": "Rezervācija #{id} nav atrasta.",
        "ok": "Labi",
        "done_confirmed": "Apstiprināts",
        "done_cancelled": "Atcelts",
        "done_deleted": "Dzēsts",
        "reply_stub": "Izvēlne"
    },
    "en": {
        "start": "👋 Hi! I'm a table booking bot.\n\nTap “{btn_book}” and answer a few questions — it's quick.",
        "choose_lang": "🌍 Choose your language:",
        "btn_book": "Reserve a table",
        "btn_menu": "View menu",
        "btn_cancel": "Cancel",
        "btn_change_lang": "🌍 Language",
        "ask_date": "🗓 Enter date (DD.MM.YYYY), e.g. 05.09.2025",
        "ask_time": "⏰ Enter time (HH:MM), e.g. 19:30",
        "ask_guests": "👥 How many guests? (number)",
        "ask_table": "🪑 Select a table:",
        "no_tables": "😕 No free tables for this time. Try another time.",
        "ask_name": "🧾 Your name for booking?",
        "ask_phone": "📞 Your phone (for confirmation)?",
        "cancelled": "Cancelled.",
        "thanks": "✅ Thanks! We received your request and will contact you soon.",
        "menu": "📋 Menu: {url}",
        "menu_empty": "📋 Menu is not yet added. Set MENU_URL in .env",
        "id": "Your chat_id: {id}",
        "err_date_format": "Enter date in DD.MM.YYYY (e.g., 05.09.2025)",
        "err_date_past": "Date is in the past",
        "err_time_format": "Enter time as 19:30 (also 19.30 or 1930 allowed).",
        "err_time_hours": "Bookings are accepted from {open} to {close}.",
        "err_guests_nan": "Enter number of guests, e.g. 2",
        "err_guests_range": "Guests from 1 to 30",
        "err_name_short": "Name is too short. Try again.",
        "err_phone_short": "Phone looks too short. Enter again.",
        "lang_set": "✅ Language saved.",
        "btn_lang_ru": "🇷🇺 Russian",
        "btn_lang_lv": "🇱🇻 Latvian",
        "btn_lang_en": "🇬🇧 English",
        "user_confirmed": "✅ Your booking is confirmed! See you soon!",
        "user_cancelled": "❌ Unfortunately, the booking was canceled. Please contact us to reschedule.",
        "admin_new": "📩 New booking:",
        "admin_note_confirmed": "✅ Confirmed by admin.",
        "admin_note_cancelled": "❌ Canceled by admin.",
        "btn_admin_confirm": "✅ Confirm",
        "btn_admin_cancel": "❌ Cancel",
        "admin_field_date": "Date",
        "admin_field_time": "Time",
        "admin_field_table": "Table",
        "admin_field_guests": "Guests",
        "admin_field_name": "Name",
        "admin_field_phone": "Phone",
        "admin_field_user": "From user",
        "btn_admin_panel": "👑 Admin panel",
        "btn_admin_delete": "🗑 Delete…",
        "admin_status_label": "Status",
        "admin_filter_all": "all",
        "admin_filter_new": "new",
        "admin_filter_confirmed": "confirmed",
        "admin_filter_cancelled": "cancelled",
        "admin_list_header": "📋 Bookings (page {page}, {status_label}: {status}):",
        "empty": "Empty.",
        "enter_booking_id": "Enter booking ID (e.g., 12)",
        "ask_id": "Specify ID: /del 12 (or just the number)",
        "id_must_be_number": "ID must be a number. Example: /del 12",
        "need_number": "Need a number. Example: 12",
        "booking_deleted": "Booking #{id} deleted.",
        "booking_not_found": "Booking #{id} not found.",
        "ok": "OK",
        "done_confirmed": "Confirmed",
        "done_cancelled": "Cancelled",
        "done_deleted": "Deleted",
        "reply_stub": "Menu"
    },
}

def pick_default_lang(tg_code: str | None) -> str:
    if not tg_code:
        return "ru"
    code = tg_code.lower()
    if code.startswith("ru"):
        return "ru"
    if code.startswith("lv") or code.startswith("lt"):
        return "lv"
    return "en"

def T(lang: str, key: str, **kwargs) -> str:
    txt = I18N.get(lang, I18N["ru"]).get(key, "")
    return txt.format(**kwargs)

# ============================= Общие настройки =============================
OPEN_TIME  = _time(10, 0)
CLOSE_TIME = _time(22, 0)
DURATION_MIN = 120
PAGE_SIZE = 10

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booking_bot")

def _parse_ids(s: str) -> set[int]:
    ids = set()
    for part in s.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids

load_dotenv()
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))
MENU_URL      = os.getenv("MENU_URL", "")
DATABASE_URL  = os.getenv("DATABASE_URL", "")

STAFF_USER_IDS: set[int] = _parse_ids(os.getenv("STAFF_USER_IDS", ""))
if ADMIN_USER_ID:
    STAFF_USER_IDS.add(ADMIN_USER_ID)

def is_staff(user_id: int | None) -> bool:
    return bool(user_id) and user_id in STAFF_USER_IDS

def can_admin(user_id: int | None, chat_id: int | None, chat_type: str | None) -> bool:
    return is_staff(user_id) and (chat_type == "private" or (ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID))

BOOK_BTN_TEXTS   = [I18N[l]["btn_book"] for l in LANGS]
MENU_BTN_TEXTS   = [I18N[l]["btn_menu"] for l in LANGS]
CANCEL_BTN_TEXTS = [I18N[l]["btn_cancel"] for l in LANGS]
CHANGE_LANG_BTN_TEXTS = [I18N[l]["btn_change_lang"] for l in LANGS]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

# ============================= Команды =============================
PUBLIC_COMMANDS = {
    "ru": [BotCommand(command="start", description="Главное меню"),
           BotCommand(command="book",  description="Забронировать столик")],
    "lv": [BotCommand(command="start", description="Galvenā izvēlne"),
           BotCommand(command="book",  description="Rezervēt galdu")],
    "en": [BotCommand(command="start", description="Main menu"),
           BotCommand(command="book",  description="Reserve a table")],
}
ADMIN_COMMANDS = {
    "ru": [BotCommand(command="admin", description="Админ-панель")],
    "lv": [BotCommand(command="admin", description="Admin panelis")],
    "en": [BotCommand(command="admin", description="Admin panel")],
}

async def set_default_commands(bot: Bot):
    for lang in ("ru", "lv", "en"):
        await bot.set_my_commands(PUBLIC_COMMANDS[lang], scope=BotCommandScopeDefault(), language_code=lang)

async def set_chat_public_commands(bot: Bot, chat_id: int, lang: str):
    await bot.set_my_commands(PUBLIC_COMMANDS.get(lang, PUBLIC_COMMANDS["ru"]), scope=BotCommandScopeChat(chat_id=chat_id))

async def set_chat_admin_commands(bot: Bot, chat_id: int, lang: str = "ru"):
    await bot.set_my_commands(ADMIN_COMMANDS.get(lang, ADMIN_COMMANDS["ru"]), scope=BotCommandScopeChat(chat_id=chat_id))

# ============================= БД =============================
POOL: asyncpg.Pool | None = None

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS tables (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    seats INT  NOT NULL CHECK (seats > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
"""
CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    lang TEXT NOT NULL DEFAULT 'ru'
);
"""
CREATE_BOOKINGS = """
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    guests INT NOT NULL CHECK (guests BETWEEN 1 AND 30),
    table_id INT REFERENCES tables(id),
    status TEXT NOT NULL DEFAULT 'new',
    duration_min INT NOT NULL DEFAULT 120,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

async def init_db_pool():
    global POOL
    POOL = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with POOL.acquire() as conn:
        await conn.execute(CREATE_TABLES)
        await conn.execute(CREATE_USERS)
        await conn.execute(CREATE_BOOKINGS)
        await conn.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS duration_min INT NOT NULL DEFAULT 120;")
        cnt = await conn.fetchval("SELECT COUNT(*) FROM tables;")
        if cnt == 0:
            await conn.executemany(
                "INSERT INTO tables(title, seats) VALUES($1, $2)",
                [("Зал №1", 4), ("Терраса", 2), ("VIP", 6)]
            )
    logger.info("Postgres pool ready")

@asynccontextmanager
async def get_conn():
    assert POOL is not None, "DB pool is not initialized"
    async with POOL.acquire() as conn:
        yield conn

async def get_lang(user_id: int, fallback: str = "ru") -> str:
    async with get_conn() as conn:
        lang = await conn.fetchval("SELECT lang FROM users WHERE user_id=$1", user_id)
    return lang or fallback

async def set_lang(user_id: int, lang: str):
    if lang not in LANGS:
        lang = "ru"
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO users(user_id, lang) VALUES($1,$2) "
            "ON CONFLICT (user_id) DO UPDATE SET lang=$2",
            user_id, lang
        )

# ============================= Клавиатуры =============================
def main_kb(lang: str, user_id: int | None = None, chat_id: int | None = None, chat_type: str | None = None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=I18N[lang]["btn_book"])],
        [KeyboardButton(text=I18N[lang]["btn_menu"])],
        [KeyboardButton(text=I18N[lang]["btn_change_lang"])],
    ]
    if can_admin(user_id, chat_id, chat_type):
        rows.append([KeyboardButton(text=I18N[lang]["btn_admin_panel"])])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def cancel_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=I18N[lang]["btn_cancel"])]], resize_keyboard=True)

# ============================= FSM состояния =============================
router = Router()
router.message.filter((F.chat.type == "private") | (F.chat.id == ADMIN_CHAT_ID))
router.callback_query.filter((F.message.chat.type == "private") | (F.message.chat.id == ADMIN_CHAT_ID))

guard = Router(name="guard")

@guard.message(F.chat.type.in_({"group", "supergroup"}))
async def auto_leave(msg: Message, bot: Bot):
    if ADMIN_CHAT_ID and msg.chat.id == ADMIN_CHAT_ID:
        return
    await bot.leave_chat(msg.chat.id)

@guard.my_chat_member()
async def on_added(ev: ChatMemberUpdated, bot: Bot):
    if ev.chat.type in {"group", "supergroup"} and ev.chat.id != ADMIN_CHAT_ID:
        new_status = ev.new_chat_member.status
        if new_status in {"member", "administrator"}:
            await bot.leave_chat(ev.chat.id)

class BookingForm(StatesGroup):
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_guests = State()
    waiting_for_table = State()
    waiting_for_name = State()
    waiting_for_phone = State()

class AdminDelete(StatesGroup):
    waiting_for_id = State()

def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=I18N["ru"]["btn_lang_ru"], callback_data="lang:ru"),
            InlineKeyboardButton(text=I18N["lv"]["btn_lang_lv"], callback_data="lang:lv"),
            InlineKeyboardButton(text=I18N["en"]["btn_lang_en"], callback_data="lang:en"),
        ]]
    )

# ============================= Валидаторы ввода =============================
def parse_date_localized(value: str, lang: str) -> _date:
    s = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt).date()
            if d < _date.today():
                raise ValueError(T(lang, "err_date_past"))
            return d
        except ValueError:
            continue
    raise ValueError(T(lang, "err_date_format"))

def parse_time_localized(value: str, lang: str) -> _time:
    s = value.strip().replace(" ", "").replace(".", ":")
    if s.isdigit() and len(s) == 4:
        s = f"{s[:2]}:{s[2:]}"
    try:
        t = datetime.strptime(s, "%H:%M").time()
        if not (OPEN_TIME <= t <= CLOSE_TIME):
            raise ValueError(T(lang, "err_time_hours", open=OPEN_TIME.strftime("%H:%M"), close=CLOSE_TIME.strftime("%H:%M")))
        return t
    except ValueError:
        raise ValueError(T(lang, "err_time_format"))

def parse_guests_localized(value: str, lang: str) -> int:
    s = value.strip().replace(" ", "")
    if not s.isdigit():
        raise ValueError(T(lang, "err_guests_nan"))
    n = int(s)
    if not (1 <= n <= 30):
        raise ValueError(T(lang, "err_guests_range"))
    return n

# ============================= Статусы =============================
async def set_status(booking_id: int, new_status: str) -> tuple[int | None, int | None]:
    async with get_conn() as conn:
        row = await conn.fetchrow(
            "UPDATE bookings SET status=$1 WHERE id=$2 RETURNING id, user_id",
            new_status, booking_id
        )
    if row:
        return row["id"], row["user_id"]
    return None, None

# ============================= Хендлеры =============================
@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    await state.clear()
    async with get_conn() as conn:
        lang = await conn.fetchval("SELECT lang FROM users WHERE user_id=$1", msg.from_user.id)
    if not lang:
        guess = pick_default_lang(msg.from_user.language_code)
        await set_lang(msg.from_user.id, guess)
        await msg.answer(T(guess, "start", btn_book=I18N[guess]["btn_book"]),
                         reply_markup=main_kb(guess, msg.from_user.id, msg.chat.id, msg.chat.type))
        await msg.answer(T(guess, "choose_lang"), reply_markup=lang_kb())
        await set_chat_public_commands(msg.bot, msg.from_user.id, guess)
        return
    await msg.answer(T(lang, "start", btn_book=I18N[lang]["btn_book"]),
                     reply_markup=main_kb(lang, msg.from_user.id, msg.chat.id, msg.chat.type))
    await set_chat_public_commands(msg.bot, msg.from_user.id, lang)


@router.message(F.text.in_(CHANGE_LANG_BTN_TEXTS))
@router.message(Command("lang"))
async def choose_lang_cmd(msg: Message):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    await msg.answer(T(lang, "choose_lang"), reply_markup=lang_kb())

@router.callback_query(F.data.startswith("lang:"))
async def set_lang_cb(cb: CallbackQuery):
    lang = cb.data.split(":")[1]
    await set_lang(cb.from_user.id, lang)
    await cb.message.edit_reply_markup()
    await cb.message.answer(T(lang, "lang_set"))
    await cb.message.answer(T(lang, "start", btn_book=I18N[lang]["btn_book"]),
                            reply_markup=main_kb(lang, cb.from_user.id, cb.message.chat.id, cb.message.chat.type))
    await set_chat_public_commands(cb.bot, cb.from_user.id, lang)
    await cb.answer()

@router.message(Command("id"))
async def get_id(msg: Message):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    await msg.answer(T(lang, "id", id=hbold(msg.chat.id)))

@router.message(F.text.in_(MENU_BTN_TEXTS))
async def show_menu(msg: Message):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    if MENU_URL:
        await msg.answer(T(lang, "menu", url=MENU_URL))
    else:
        await msg.answer(T(lang, "menu_empty"))

@router.message(Command("book"))
@router.message(F.text.in_(BOOK_BTN_TEXTS))
async def book_start(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    await state.clear()
    await state.set_state(BookingForm.waiting_for_date)
    await msg.answer(T(lang, "ask_date"), reply_markup=cancel_kb(lang))

@router.message(F.text.in_(CANCEL_BTN_TEXTS))
async def cancel(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    await state.clear()
    await msg.answer(T(lang, "cancelled"), reply_markup=main_kb(lang, msg.from_user.id, msg.chat.id, msg.chat.type))

@router.message(BookingForm.waiting_for_date)
async def step_date(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    try:
        d = parse_date_localized(msg.text, lang)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(booking_date=d.isoformat())
    await state.set_state(BookingForm.waiting_for_time)
    await msg.answer(T(lang, "ask_time"))

@router.message(BookingForm.waiting_for_time)
async def step_time(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    try:
        t = parse_time_localized(msg.text, lang)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(booking_time=t.strftime("%H:%M"))
    await state.set_state(BookingForm.waiting_for_guests)
    await msg.answer(T(lang, "ask_guests"))

@router.message(BookingForm.waiting_for_guests)
async def step_guests(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    try:
        guests = parse_guests_localized(msg.text, lang)
    except ValueError as e:
        await msg.answer(str(e)); return
    await state.update_data(guests=guests)

    data = await state.get_data()
    new_date = _date.fromisoformat(data["booking_date"])
    new_start = _time.fromisoformat(data["booking_time"])
    new_start_dt = datetime.combine(new_date, new_start)
    new_end_dt = new_start_dt + timedelta(minutes=DURATION_MIN)

    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.seats
            FROM tables t
            WHERE t.is_active = TRUE
              AND t.seats >= $1
              AND t.id NOT IN (
                    SELECT b.table_id
                    FROM bookings b
                    WHERE b.booking_date = $2
                      AND b.status IN ('new','confirmed')
                      AND b.table_id IS NOT NULL
                      AND (
                            b.booking_time < $3::time
                        AND (b.booking_time + (b.duration_min || ' minutes')::interval) > $4::time
                      )
              )
            ORDER BY t.seats, t.title
            """,
            int(guests), new_date, new_end_dt.time(), new_start
        )

    if not rows:
        await msg.answer(T(lang, "no_tables"))
        await state.set_state(BookingForm.waiting_for_time)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{r['title']} — {r['seats']} мест", callback_data=f"pick_table:{r['id']}")]
            for r in rows
        ]
    )
    await state.set_state(BookingForm.waiting_for_table)
    await msg.answer(T(lang, "ask_table"), reply_markup=kb)

@router.callback_query(F.data.startswith("pick_table:"))
async def pick_table(cb: CallbackQuery, state: FSMContext):
    lang = await get_lang(cb.from_user.id, pick_default_lang(cb.from_user.language_code))
    table_id = int(cb.data.split(":")[1])
    await state.update_data(table_id=table_id)
    await state.set_state(BookingForm.waiting_for_name)
    await cb.message.edit_reply_markup()
    await cb.message.answer(T(lang, "ask_name"))
    await cb.answer()

@router.message(BookingForm.waiting_for_name)
async def step_name(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    name = msg.text.strip()
    if len(name) < 2:
        await msg.answer(T(lang, "err_name_short")); return
    await state.update_data(name=name)
    await state.set_state(BookingForm.waiting_for_phone)
    await msg.answer(T(lang, "ask_phone"))

@router.message(BookingForm.waiting_for_phone)
async def step_phone(msg: Message, state: FSMContext):
    lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    phone = msg.text.strip()
    if len(phone) < 6:
        await msg.answer(T(lang, "err_phone_short")); return

    data = await state.get_data()
    data.update({"phone": phone, "user_id": msg.from_user.id})

    booking_date = _date.fromisoformat(data["booking_date"])
    booking_time = _time.fromisoformat(data["booking_time"])
    created_at   = datetime.now(UTC)

    async with get_conn() as conn:
        booking_id = await conn.fetchval(
            """
            INSERT INTO bookings
              (user_id, name, phone, booking_date, booking_time, guests, table_id, created_at, status, duration_min)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'new',$9)
            RETURNING id
            """,
            data["user_id"], data["name"], data["phone"],
            booking_date, booking_time, int(data["guests"]),
            int(data.get("table_id") or 0),
            created_at,
            DURATION_MIN
        )
        logger.info("Booking saved id=%s", booking_id)

    user_lang = await get_lang(msg.from_user.id, pick_default_lang(msg.from_user.language_code))
    admin_text = (
        f"{T(user_lang, 'admin_new')}\n"
        f"{T(user_lang, 'admin_field_date')}: {data['booking_date']}\n"
        f"{T(user_lang, 'admin_field_time')}: {data['booking_time']}\n"
        f"{T(user_lang, 'admin_field_table')}: {data.get('table_id') or '—'}\n"
        f"{T(user_lang, 'admin_field_guests')}: {data['guests']}\n"
        f"{T(user_lang, 'admin_field_name')}: {data['name']}\n"
        f"{T(user_lang, 'admin_field_phone')}: {data['phone']}\n"
        f"{T(user_lang, 'admin_field_user')}: @{msg.from_user.username or msg.from_user.id}"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=T(user_lang, "btn_admin_confirm"), callback_data=f"adm:confirm:{booking_id}"),
            InlineKeyboardButton(text=T(user_lang, "btn_admin_cancel"),  callback_data=f"adm:cancel:{booking_id}"),
            InlineKeyboardButton(text=I18N[user_lang]["btn_admin_delete"], callback_data=f"ap:delete:{booking_id}")
        ]]
    )
    try:
        if ADMIN_CHAT_ID:
            await msg.bot.send_message(ADMIN_CHAT_ID, admin_text, reply_markup=kb)
    except Exception as e:
        logger.exception("Не удалось отправить уведомление администратору: %s", e)

    await state.clear()
    await msg.answer(T(lang, "thanks"), reply_markup=main_kb(lang, msg.from_user.id, msg.chat.id, msg.chat.type))

# ===== Удаление по ID =====
@router.callback_query(F.data.startswith("ap:delask:"))
async def ap_delask(cb: CallbackQuery, state: FSMContext):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    await state.set_state(AdminDelete.waiting_for_id)
    await cb.message.answer("Введите номер брони (ID), например: 12")
    await cb.answer()

@router.message(Command("del"))
async def del_cmd(msg: Message, state: FSMContext):
    if not can_admin(msg.from_user.id, msg.chat.id, msg.chat.type):
        return
    parts = (msg.text or "").split()
    if len(parts) < 2:
        await state.set_state(AdminDelete.waiting_for_id)
        return await msg.answer("Укажи ID: /del 12  (или просто напиши число)")
    bid_str = parts[1].lstrip("#")
    if not bid_str.isdigit():
        return await msg.answer("ID должен быть числом. Пример: /del 12")
    bid = int(bid_str)
    async with get_conn() as conn:
        row = await conn.fetchrow("DELETE FROM bookings WHERE id=$1 RETURNING id", bid)
    await msg.answer(f"Бронь #{bid} удалена." if row else f"Бронь #{bid} не найдена.")

@router.message(StateFilter(AdminDelete.waiting_for_id), F.text.regexp(r"^\s*#?\d+\s*$"), flags={"block": True})
async def ap_delete_by_id_input(msg: Message, state: FSMContext):
    if not can_admin(msg.from_user.id, msg.chat.id, msg.chat.type):
        return
    bid = int((msg.text or "").strip().lstrip("#"))
    async with get_conn() as conn:
        row = await conn.fetchrow("DELETE FROM bookings WHERE id=$1 RETURNING id", bid)
    await state.clear()
    await msg.answer(f"Бронь #{bid} удалена." if row else f"Бронь #{bid} не найдена.")

@router.message(StateFilter(AdminDelete.waiting_for_id), flags={"block": True})
async def ap_delete_by_id_wrong(msg: Message):
    if (msg.text or "").startswith("/"):
        return
    await msg.answer("Нужно число. Пример: 12")

# ===== Коллбеки админа из уведомлений =====
@router.callback_query(F.data.startswith("adm:confirm:"))
async def admin_confirm(cb: CallbackQuery):
    booking_id = int(cb.data.split(":")[2])
    bid, user_id = await set_status(booking_id, "confirmed")
    if not bid:
        return await cb.answer("Бронь не найдена", show_alert=True)
    user_lang = await get_lang(user_id, "ru")
    await cb.message.edit_text(cb.message.text + f"\n\n{T(user_lang, 'admin_note_confirmed')}")
    try:
        await cb.bot.send_message(user_id, T(user_lang, "user_confirmed"))
    except Exception:
        pass
    await cb.answer("OK")

@router.callback_query(F.data.startswith("adm:cancel:"))
async def admin_cancel(cb: CallbackQuery):
    booking_id = int(cb.data.split(":")[2])
    bid, user_id = await set_status(booking_id, "cancelled")
    if not bid:
        return await cb.answer("Бронь не найдена", show_alert=True)
    user_lang = await get_lang(user_id, "ru")
    await cb.message.edit_text(cb.message.text + f"\n\n{T(user_lang, 'admin_note_cancelled')}")
    try:
        await cb.bot.send_message(user_id, T(user_lang, "user_cancelled"))
    except Exception:
        pass
    await cb.answer("OK")

# ===== Мини-панель админа (/admin) =====
def fmt_admin_booking_line(row, lang: str) -> str:
    return (f"#{row['id']} — {row['booking_date']} {row['booking_time']}, "
            f"{T(lang,'admin_field_table').lower()}:{row['table_id'] or '—'}, "
            f"{T(lang,'admin_field_guests').lower()}:{row['guests']}, "
            f"{row['name']} ({row['phone']}) [{row['status']}]")

async def fetch_bookings(page: int = 0, status: str = "all"):
    offset = page * PAGE_SIZE
    where = "" if status == "all" else "WHERE status = $1"
    params = [] if status == "all" else [status]
    query = f"""
        SELECT id, user_id, name, phone, booking_date, booking_time,
               guests, table_id, status, created_at
        FROM bookings
        {where}
        ORDER BY booking_date DESC, booking_time DESC, id DESC
        LIMIT {PAGE_SIZE} OFFSET {offset}
    """
    async with get_conn() as conn:
        rows = await conn.fetch(query, *params)
    return rows

def admin_list_kb(page: int, status: str, lang: str = "ru") -> InlineKeyboardMarkup:
    status_disp = {
        "all": I18N[lang]["admin_filter_all"],
        "new": I18N[lang]["admin_filter_new"],
        "confirmed": I18N[lang]["admin_filter_confirmed"],
        "cancelled": I18N[lang]["admin_filter_cancelled"],
    }.get(status, status)
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⬅️", callback_data=f"ap:page:{max(page-1,0)}:{status}"),
            InlineKeyboardButton(text=f"{I18N[lang]['admin_status_label']}: {status_disp}", callback_data="ap:nop"),
            InlineKeyboardButton(text="➡️", callback_data=f"ap:page:{page+1}:{status}"),
        ],
        [
            InlineKeyboardButton(text=I18N[lang]["admin_filter_all"],       callback_data=f"ap:set_status:{page}:all"),
            InlineKeyboardButton(text=I18N[lang]["admin_filter_new"],       callback_data=f"ap:set_status:{page}:new"),
            InlineKeyboardButton(text=I18N[lang]["admin_filter_confirmed"], callback_data=f"ap:set_status:{page}:confirmed"),
            InlineKeyboardButton(text=I18N[lang]["admin_filter_cancelled"], callback_data=f"ap:set_status:{page}:cancelled"),
        ],
        [InlineKeyboardButton(text=I18N[lang]["btn_admin_delete"], callback_data=f"ap:delask:{page}:{status}")]
    ])

@router.callback_query(F.data == "ap:nop")
async def ap_nop(cb: CallbackQuery):
    await cb.answer()

@router.message(F.text == I18N["ru"]["btn_admin_panel"])
@router.message(F.text == I18N["lv"]["btn_admin_panel"])
@router.message(F.text == I18N["en"]["btn_admin_panel"])
@router.message(Command("admin"))
async def admin_panel(msg: Message):
    if not can_admin(msg.from_user.id, msg.chat.id, msg.chat.type):
        return
    lang = await get_lang(msg.from_user.id, "ru")
    status = "all"
    status_disp = {
        "all": I18N[lang]["admin_filter_all"],
        "new": I18N[lang]["admin_filter_new"],
        "confirmed": I18N[lang]["admin_filter_confirmed"],
        "cancelled": I18N[lang]["admin_filter_cancelled"],
    }[status]
    rows = await fetch_bookings(page=0, status=status)
    header = T(lang, "admin_list_header", page=1, status_label=I18N[lang]["admin_status_label"], status=status_disp)
    text = header + "\n\n" + ("\n".join([fmt_admin_booking_line(r, lang) for r in rows]) if rows else T(lang,"empty"))
    await msg.answer(text, reply_markup=admin_list_kb(0, status, lang))
    await msg.answer("🤗", reply_markup=main_kb(lang, msg.from_user.id, msg.chat.id, msg.chat.type))

@router.message(AdminDelete.waiting_for_id)
async def ap_delete_waiting(msg: Message, state: FSMContext):
    if not can_admin(msg.from_user.id, msg.chat.id, msg.chat.type):
        return
    txt = (msg.text or "").strip()
    if txt.startswith("/"):
        return
    bid_str = txt.lstrip("#").replace(" ", "")
    if not bid_str.isdigit():
        return await msg.answer("Нужно число. Пример: 12")
    bid = int(bid_str)
    async with get_conn() as conn:
        row = await conn.fetchrow("DELETE FROM bookings WHERE id=$1 RETURNING id", bid)
    await state.clear()
    await msg.answer(f"Бронь #{bid} удалена." if row else f"Бронь #{bid} не найдена.")

@router.callback_query(F.data.startswith("ap:page:"))
async def ap_page(cb: CallbackQuery):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    _, _, page_str, status = cb.data.split(":")
    page = max(int(page_str), 0)
    lang = await get_lang(cb.from_user.id, "ru")
    status_disp = {
        "all": I18N[lang]["admin_filter_all"],
        "new": I18N[lang]["admin_filter_new"],
        "confirmed": I18N[lang]["admin_filter_confirmed"],
        "cancelled": I18N[lang]["admin_filter_cancelled"],
    }.get(status, status)
    rows = await fetch_bookings(page=page, status=status)
    header = T(lang, "admin_list_header", page=page+1, status_label=I18N[lang]["admin_status_label"], status=status_disp)
    text = header + "\n\n" + ("\n".join([fmt_admin_booking_line(r, lang) for r in rows]) if rows else T(lang, "empty"))
    try:
        await cb.message.edit_text(text, reply_markup=admin_list_kb(page, status, lang))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await cb.answer()

@router.callback_query(F.data.startswith("ap:set_status:"))
async def ap_set_status(cb: CallbackQuery):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    _, _, page_str, status = cb.data.split(":")
    page = max(int(page_str), 0)
    lang = await get_lang(cb.from_user.id, "ru")
    status_disp = {
        "all": I18N[lang]["admin_filter_all"],
        "new": I18N[lang]["admin_filter_new"],
        "confirmed": I18N[lang]["admin_filter_confirmed"],
        "cancelled": I18N[lang]["admin_filter_cancelled"],
    }.get(status, status)
    rows = await fetch_bookings(page=page, status=status)
    header = T(lang, "admin_list_header", page=page+1, status_label=I18N[lang]["admin_status_label"], status=status_disp)
    text = header + "\n\n" + ("\n".join([fmt_admin_booking_line(r, lang) for r in rows]) if rows else T(lang, "empty"))
    try:
        await cb.message.edit_text(text, reply_markup=admin_list_kb(page, status, lang))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await cb.answer(I18N[lang]["admin_status_label"] + " ✓")

@router.callback_query(F.data.startswith("ap:confirm:"))
async def ap_confirm(cb: CallbackQuery):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    bid = int(cb.data.split(":")[2])
    _, user_id = await set_status(bid, "confirmed")
    lang = await get_lang(user_id, "ru")
    try:
        await cb.bot.send_message(user_id, T(lang, "user_confirmed"))
    except Exception:
        pass
    await cb.answer("Подтверждено")

@router.callback_query(F.data.startswith("ap:cancel:"))
async def ap_cancel(cb: CallbackQuery):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    bid = int(cb.data.split(":")[2])
    _, user_id = await set_status(bid, "cancelled")
    lang = await get_lang(user_id, "ru")
    try:
        await cb.bot.send_message(user_id, T(lang, "user_cancelled"))
    except Exception:
        pass
    await cb.answer("Отменено")

@router.callback_query(F.data.startswith("ap:delete:"))
async def ap_delete(cb: CallbackQuery):
    if not can_admin(cb.from_user.id, cb.message.chat.id, cb.message.chat.type):
        return await cb.answer()
    bid = int(cb.data.split(":")[2])
    async with get_conn() as conn:
        await conn.execute("DELETE FROM bookings WHERE id=$1", bid)
    await cb.answer("Удалено")

@router.message(Command("whoami"))
async def whoami(msg: Message):
    await msg.reply(
        f"user_id: {msg.from_user.id}\n"
        f"chat_id: {msg.chat.id}\n"
        f"username: @{msg.from_user.username or '—'}\n"
        f"name: {msg.from_user.full_name}"
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
