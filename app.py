# app.py
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update
from dotenv import load_dotenv

# импортируем твои функции/объекты из main.py
# ВАЖНО: в main.py не должно вызываться asyncio.run(main()) при импорте.
from main import (
    router,
    init_db_pool,             # async
    ADMIN_CHAT_ID,            # просто чтобы .env гарантированно прогрузился
    BOT_TOKEN,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("booking_webhook")

load_dotenv()
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")  # например: https://your-service.onrender.com
if not WEBHOOK_BASE_URL:
    raise RuntimeError("WEBHOOK_BASE_URL is not set in .env")

# Глобальные объекты (инициализируем в старте)
bot: Bot | None = None
dp: Dispatcher | None = None

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    global bot, dp
    # База
    await init_db_pool()
    # Бот и диспетчер
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)
    # Команды (по желанию)
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="book", description="Забронировать столик"),
    ])
    # Вебхук
    webhook_url = f"{WEBHOOK_BASE_URL}/webhook/{BOT_TOKEN}"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook set: %s", webhook_url)

@app.on_event("shutdown")
async def on_shutdown():
    if bot:
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.session.close()

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    # простая защита: обрабатываем только наш токен
    if token != BOT_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")

    update_dict = await request.json()
    update = Update.model_validate(update_dict)

    assert bot is not None and dp is not None
    await dp.feed_update(bot, update)  # передаём апдейт в aiogram
    return {"ok": True}
